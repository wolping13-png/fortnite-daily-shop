from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from random_wolf import build_random_wolf
from send_qq_shop import (
    build_message,
    load_config,
    make_safe_image,
    normalize_base_url,
    normalize_group_ids,
    post_onebot,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "qq_bot_config.json"
GEMINI_CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"


def load_tavily_api_key() -> str:
    if os.environ.get("TAVILY_API_KEY"):
        return str(os.environ["TAVILY_API_KEY"])
    if not GEMINI_CONFIG_PATH.exists():
        return ""
    try:
        data = json.loads(GEMINI_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("tavily_api_key") or "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a random cute wolf photo to QQ groups.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to qq_bot_config.json.")
    parser.add_argument("--onebot-url", help="OneBot HTTP URL, for example http://127.0.0.1:3000.")
    parser.add_argument("--access-token", help="OneBot access token, if enabled in NapCatQQ.")
    parser.add_argument("--group-id", action="append", help="QQ group ID. Can be provided multiple times.")
    parser.add_argument("--caption", default="每日一狼", help="Text shown above the image.")
    parser.add_argument("--dry-run", action="store_true", help="Generate image and print config without sending.")
    return parser.parse_args()


def send_wolf_to_groups(
    base_url: str,
    group_ids: list[int | str],
    access_token: str,
    caption: str,
    image_path: Path,
) -> None:
    for group_id in group_ids:
        message = build_message(caption=caption, image_path=image_path)
        result = post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={"group_id": group_id, "message": message},
            access_token=access_token,
            timeout=120,
        )

        if result.get("_napcat_callback_timeout"):
            print("NapCat callback timed out. Retrying with a smaller safe image.")
            safe_path = make_safe_image(image_path)
            safe_message = build_message(caption=f"{caption}\n原图回执超时，已改发压缩版。", image_path=safe_path)
            result = post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={"group_id": group_id, "message": safe_message},
                access_token=access_token,
                timeout=120,
            )

        message_id = result.get("data", {}).get("message_id") if isinstance(result.get("data"), dict) else None
        suffix = f" message_id={message_id}" if message_id else ""
        print(f"Sent wolf image to group {group_id}.{suffix}")


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    base_url = normalize_base_url(args.onebot_url or str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    group_ids = normalize_group_ids(args.group_id or config.get("group_ids"))
    access_token = args.access_token
    if access_token is None:
        access_token = str(config.get("access_token") or "")

    generated_caption, image_path, item = build_random_wolf(tavily_api_key=load_tavily_api_key())
    caption = args.caption or generated_caption

    if args.dry_run:
        print(caption)
        print(f"Image: {image_path}")
        print(f"Groups: {group_ids}")
        print(f"Source: {item.get('image_url', '')}")
        return 0

    send_wolf_to_groups(
        base_url=base_url,
        group_ids=group_ids,
        access_token=access_token,
        caption=caption,
        image_path=image_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
