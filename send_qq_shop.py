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
SAFE_IMAGE_MAX_BYTES = 450_000


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


def make_safe_image(path: Path) -> Path:
    if not path.exists():
        return path

    target = path.with_name(f"{path.stem}_safe.jpg")
    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        max_width = 420
        max_height = 3600

        if image.width > max_width:
            height = int(image.height * max_width / image.width)
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)

        if image.height > max_height:
            width = int(image.width * max_height / image.height)
            image = image.resize((width, max_height), Image.Resampling.LANCZOS)

        for quality in (58, 52, 46, 40, 34, 30):
            image.save(target, quality=quality, optimize=True)
            if target.stat().st_size <= SAFE_IMAGE_MAX_BYTES:
                return target

        return target
    except Exception:
        return path


def split_image_vertically(path: Path, parts: int = 2) -> list[Path]:
    if not path.exists():
        return []

    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
    except Exception:
        return []

    count = max(2, min(parts, 2))
    result: list[Path] = []
    for index in range(count):
        top = int(image.height * index / count)
        bottom = int(image.height * (index + 1) / count)
        if bottom <= top:
            continue
        crop = image.crop((0, top, image.width, bottom))
        target = path.with_name(f"{path.stem}_part{index + 1}.jpg")

        working = crop
        max_width = 760
        if working.width > max_width:
            height = int(working.height * max_width / working.width)
            working = working.resize((max_width, height), Image.Resampling.LANCZOS)

        for quality in (76, 70, 64, 58, 52, 46):
            working.save(target, quality=quality, optimize=True)
            if target.stat().st_size <= SAFE_IMAGE_MAX_BYTES:
                break
        result.append(target)
    return result


def choose_send_image(path: Path, image_url: str | None = None) -> Path:
    if image_url:
        return path

    try:
        if path.exists() and path.stat().st_size > SAFE_IMAGE_MAX_BYTES:
            return make_safe_image(path)
    except Exception:
        return path

    return path


def is_napcat_callback_timeout_success(data: dict[str, Any]) -> bool:
    wording = str(data.get("wording") or data.get("message") or "")
    retcode = data.get("retcode")
    return retcode in {200, "200"} and "Timeout:" in wording and '"result": 0' in wording


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
        if is_napcat_callback_timeout_success(data):
            data["_napcat_callback_timeout"] = True
            return data
        raise RuntimeError(f"OneBot returned an error: {json.dumps(data, ensure_ascii=False)}")

    return data


def send_to_groups(
    base_url: str,
    group_ids: list[int | str],
    caption: str,
    image_path: Path,
    image_url: str | None,
    access_token: str,
) -> None:
    for group_id in group_ids:
        message = build_message(caption=caption, image_path=image_path, image_url=image_url)
        result = post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={"group_id": group_id, "message": message},
            access_token=access_token,
            timeout=120,
        )

        if result.get("_napcat_callback_timeout"):
            print("NapCat callback timed out. Splitting the shop image into two parts.")
            split_paths = split_image_vertically(image_path, parts=2)
            if split_paths:
                for index, part_path in enumerate(split_paths, 1):
                    part_caption = f"{caption}\n总图过长，已切成 2 张发送（{index}/2）"
                    retry = post_onebot(
                        base_url=base_url,
                        action="send_group_msg",
                        payload={"group_id": group_id, "message": build_message(part_caption, part_path, image_url=None)},
                        access_token=access_token,
                        timeout=120,
                    )
                    if retry.get("_napcat_callback_timeout"):
                        print(f"Split shop image callback timed out for group {group_id}: {part_path.name}")
                print(f"Sent split shop image to group {group_id}.")
                continue

            safe_path = make_safe_image(image_path)
            retry = post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={
                    "group_id": group_id,
                    "message": build_message(f"{caption}\n原图发送失败，已改发压缩版。", safe_path, image_url=None),
                },
                access_token=access_token,
                timeout=120,
            )
            if retry.get("_napcat_callback_timeout"):
                try:
                    post_onebot(
                        base_url=base_url,
                        action="send_group_msg",
                        payload={
                            "group_id": group_id,
                            "message": [
                                {
                                    "type": "text",
                                    "data": {
                                        "text": "商店图片发送被 QQ 回执卡住了。已经尝试切成 2 张发送，还是失败的话请稍后再试。"
                                    },
                                }
                            ],
                        },
                        access_token=access_token,
                        timeout=60,
                    )
                except Exception as exc:
                    print(f"Failed to send timeout notice to group {group_id}: {exc}", file=sys.stderr)
                print(f"Safe image callback also timed out for group {group_id}.")
                continue
            result = retry

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

    send_to_groups(
        base_url=base_url,
        group_ids=group_ids,
        caption=caption,
        image_path=image_path,
        image_url=image_url,
        access_token=access_token,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Failed to send QQ shop image: {exc}", file=sys.stderr)
        raise SystemExit(1)
