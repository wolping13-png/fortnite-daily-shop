from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reddit_pets import build_reddit_pet_update
from send_qq_shop import build_message, load_config, normalize_base_url, normalize_group_ids, post_onebot


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "qq_bot_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Reddit pet hot posts to QQ groups.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to qq_bot_config.json.")
    parser.add_argument("--onebot-url", help="OneBot HTTP URL, for example http://127.0.0.1:3000.")
    parser.add_argument("--access-token", help="OneBot access token, if enabled in NapCatQQ.")
    parser.add_argument("--group-id", action="append", help="QQ group ID. Can be provided multiple times.")
    parser.add_argument("--limit", type=int, default=5, help="Number of Reddit posts to include.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    base_url = normalize_base_url(args.onebot_url or str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    group_ids = normalize_group_ids(args.group_id or config.get("group_ids"))
    access_token = args.access_token
    if access_token is None:
        access_token = str(config.get("access_token") or "")

    caption, image_path, posts = build_reddit_pet_update(limit=max(1, min(args.limit, 8)))
    if not posts:
        raise RuntimeError("No Reddit pet posts were found.")

    message = build_message(caption=caption, image_path=image_path)
    for group_id in group_ids:
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={"group_id": group_id, "message": message},
            access_token=access_token,
            timeout=120,
        )
        print(f"Sent Reddit pet update to group {group_id}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Failed to send Reddit pet update: {exc}", file=sys.stderr)
        raise SystemExit(1)
