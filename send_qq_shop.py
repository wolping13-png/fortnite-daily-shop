from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "qq_bot_config.json"
DEFAULT_IMAGE_PATH = BASE_DIR / "shop.png"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")

    return data


def normalize_base_url(value: str) -> str:
    url = value.strip()
    if not url:
        raise ValueError("OneBot HTTP URL is required.")

    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"

    return url.rstrip("/") + "/"


def normalize_group_ids(value: Any) -> list[int | str]:
    if isinstance(value, (str, int)):
        value = [value]

    if not isinstance(value, list):
        raise ValueError("group_ids must be a list, string, or number.")

    group_ids: list[int | str] = []
    for item in value:
        if isinstance(item, int):
            group_ids.append(item)
            continue

        text = str(item).strip()
        if not text:
            continue
        group_ids.append(int(text) if text.isdigit() else text)

    if not group_ids:
        raise ValueError("At least one QQ group ID is required.")

    return group_ids


def encode_image(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"base64://{data}"


def build_message(caption: str, image_path: Path, image_url: str | None = None) -> list[dict[str, Any]]:
    image_file = image_url.strip() if image_url else encode_image(image_path)

    message: list[dict[str, Any]] = []
    if caption.strip():
        message.append({"type": "text", "data": {"text": caption.strip() + "\n"}})
    message.append({"type": "image", "data": {"file": image_file}})
    return message


def post_onebot(
    base_url: str,
    action: str,
    payload: dict[str, Any],
    access_token: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    import requests

    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    response = requests.post(
        urljoin(base_url, action),
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected OneBot response: {data!r}")

    status = str(data.get("status", "")).lower()
    retcode = data.get("retcode")
    if status not in {"ok", "async"} and retcode not in {0, "0"}:
        raise RuntimeError(f"OneBot returned an error: {json.dumps(data, ensure_ascii=False)}")

    return data


def send_to_groups(
    base_url: str,
    group_ids: list[int | str],
    message: list[dict[str, Any]],
    access_token: str,
) -> None:
    for group_id in group_ids:
        result = post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={"group_id": group_id, "message": message},
            access_token=access_token,
        )
        message_id = result.get("data", {}).get("message_id") if isinstance(result.get("data"), dict) else None
        suffix = f" message_id={message_id}" if message_id else ""
        print(f"Sent shop image to group {group_id}.{suffix}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Fortnite shop image to QQ groups through OneBot HTTP.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to qq_bot_config.json.")
    parser.add_argument("--onebot-url", help="OneBot HTTP URL, for example http://127.0.0.1:3000.")
    parser.add_argument("--access-token", help="OneBot access token, if enabled in NapCatQQ.")
    parser.add_argument("--group-id", action="append", help="QQ group ID. Can be provided multiple times.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE_PATH), help="Image path to send.")
    parser.add_argument("--image-url", help="Send an image URL instead of local base64 data.")
    parser.add_argument("--caption", help="Text shown above the image.")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved config without sending.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))

    base_url = normalize_base_url(
        args.onebot_url
        or str(config.get("onebot_http_url") or "http://127.0.0.1:3000")
    )
    group_ids = normalize_group_ids(args.group_id or config.get("group_ids"))
    access_token = args.access_token
    if access_token is None:
        access_token = str(config.get("access_token") or "")

    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = BASE_DIR / image_path

    caption = args.caption
    if caption is None:
        caption = str(config.get("caption") or "Fortnite Daily Shop")

    image_url = args.image_url or config.get("image_url")

    if args.dry_run:
        print(
            json.dumps(
                {
                    "onebot_http_url": base_url,
                    "group_ids": group_ids,
                    "image": str(image_path),
                    "image_url": image_url or "",
                    "caption": caption,
                    "access_token_set": bool(access_token),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    message = build_message(caption=caption, image_path=image_path, image_url=image_url)
    send_to_groups(base_url=base_url, group_ids=group_ids, message=message, access_token=access_token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Failed to send QQ shop image: {exc}", file=sys.stderr)
        raise SystemExit(1)
