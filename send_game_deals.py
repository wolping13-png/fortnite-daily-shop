from __future__ import annotations

import argparse
from pathlib import Path

from game_deals import build_game_deals_update
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Steam discounts and Epic free games to QQ groups.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to qq_bot_config.json.")
    parser.add_argument("--onebot-url", help="OneBot HTTP URL, for example http://127.0.0.1:3000.")
    parser.add_argument("--access-token", help="OneBot access token, if enabled in NapCatQQ.")
    parser.add_argument("--group-id", action="append", help="QQ group ID. Can be provided multiple times.")
    parser.add_argument("--steam-limit", type=int, default=12, help="How many Steam deals to include.")
    parser.add_argument("--epic-country", default="CN", help="Epic country code, default CN.")
    parser.add_argument("--dry-run", action="store_true", help="Generate image and print config without sending.")
    return parser.parse_args()


def send_game_deals_to_groups(
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
        print(f"Sent game deals to group {group_id}.{suffix}")


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    base_url = normalize_base_url(args.onebot_url or str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    group_ids = normalize_group_ids(args.group_id or config.get("group_ids"))
    access_token = args.access_token
    if access_token is None:
        access_token = str(config.get("access_token") or "")

    caption, image_path, data = build_game_deals_update(steam_limit=args.steam_limit, epic_country=args.epic_country)
    if args.dry_run:
        print(caption)
        print(f"Image: {image_path}")
        print(f"Groups: {group_ids}")
        if data.get("errors"):
            print(f"Errors: {data['errors']}")
        return 0

    send_game_deals_to_groups(
        base_url=base_url,
        group_ids=group_ids,
        access_token=access_token,
        caption=caption,
        image_path=image_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
