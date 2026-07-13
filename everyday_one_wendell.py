from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from send_qq_shop import normalize_base_url, post_onebot
from x_posts import clean_text, normalize_bearer_token


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"
CACHE_DIR = BASE_DIR / ".cache" / "everyone_wendell"
STATE_PATH = CACHE_DIR / "state.json"
MEDIA_DIR = CACHE_DIR / "media"
X_USER_BY_USERNAME_URL = "https://api.x.com/2/users/by/username/{username}"
X_USER_POSTS_URL = "https://api.x.com/2/users/{user_id}/tweets"
DEFAULT_USERNAME = "wendellindashop"


def china_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return datetime.now(timezone.utc).astimezone()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def normalized_group_ids(value: Any) -> list[int | str]:
    if isinstance(value, (str, int)):
        value = [value]
    result: list[int | str] = []
    for item in value if isinstance(value, list) else []:
        text = str(item).strip()
        if text and text not in {str(existing) for existing in result}:
            result.append(int(text) if text.isdigit() else text)
    return result


def configured_group_ids(config: dict[str, Any]) -> list[int | str]:
    return normalized_group_ids(
        config.get("everyone_wendell_group_ids")
        or config.get("allowed_group_ids")
        or config.get("group_ids")
    )


def x_get(url: str, bearer_token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {normalize_bearer_token(bearer_token)}",
            "User-Agent": "EveryOneWendell/1.0",
        },
        params=params or {},
        timeout=35,
    )
    if response.status_code in {401, 403}:
        raise RuntimeError(f"X API token has no access: {response.text[:500]}")
    if response.status_code == 429:
        raise RuntimeError("X API rate limit or credits are exhausted.")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("X API returned an unexpected response.")
    return data


def resolve_author(
    bearer_token: str,
    username: str,
    state: dict[str, Any],
) -> dict[str, str]:
    cached = state.get("author") if isinstance(state.get("author"), dict) else {}
    if str(cached.get("username") or "").lower() == username.lower() and cached.get("id"):
        return {key: str(cached.get(key) or "") for key in ("id", "username", "name", "profile_image_url")}

    data = x_get(
        X_USER_BY_USERNAME_URL.format(username=quote(username.lstrip("@"))),
        bearer_token,
        {"user.fields": "name,username,profile_image_url"},
    )
    user = data.get("data") if isinstance(data.get("data"), dict) else {}
    if not user.get("id"):
        raise RuntimeError(f"Could not find X author @{username}.")
    author = {key: str(user.get(key) or "") for key in ("id", "username", "name", "profile_image_url")}
    state["author"] = author
    return author


def fetch_author_posts(
    bearer_token: str,
    author_id: str,
    since_id: str = "",
    fetch_limit: int = 5,
) -> dict[str, Any]:
    params = {
        "max_results": str(max(5, min(int(fetch_limit or 5), 100))),
        "tweet.fields": "created_at,author_id,attachments,referenced_tweets,possibly_sensitive",
        "expansions": (
            "attachments.media_keys,referenced_tweets.id,"
            "referenced_tweets.id.author_id,referenced_tweets.id.attachments.media_keys"
        ),
        "media.fields": "media_key,type,url,preview_image_url,variants,width,height,alt_text",
        "user.fields": "name,username,profile_image_url",
    }
    if since_id:
        params["since_id"] = since_id
    return x_get(X_USER_POSTS_URL.format(user_id=author_id), bearer_token, params)


def best_video_variant(media: dict[str, Any]) -> dict[str, Any]:
    variants = [
        item
        for item in media.get("variants", []) or []
        if isinstance(item, dict)
        and str(item.get("content_type") or "").lower() == "video/mp4"
        and str(item.get("url") or "").strip()
    ]
    if not variants:
        return {}
    return max(variants, key=lambda item: int(item.get("bit_rate") or 0))


def normalize_media(media: dict[str, Any]) -> dict[str, Any] | None:
    media_type = str(media.get("type") or "").lower()
    if media_type == "photo":
        url = str(media.get("url") or "").strip()
        if not url:
            return None
        return {
            "type": "photo",
            "url": url,
            "preview_url": url,
            "width": int(media.get("width") or 0),
            "height": int(media.get("height") or 0),
            "alt_text": str(media.get("alt_text") or ""),
        }

    if media_type in {"video", "animated_gif"}:
        variant = best_video_variant(media)
        url = str(variant.get("url") or "").strip()
        preview_url = str(media.get("preview_image_url") or "").strip()
        if not url and preview_url:
            return {
                "type": "photo",
                "url": preview_url,
                "preview_url": preview_url,
                "fallback_for": media_type,
            }
        if not url:
            return None
        return {
            "type": media_type,
            "url": url,
            "preview_url": preview_url,
            "bit_rate": int(variant.get("bit_rate") or 0),
            "width": int(media.get("width") or 0),
            "height": int(media.get("height") or 0),
            "alt_text": str(media.get("alt_text") or ""),
        }
    return None


def normalize_candidates(
    data: dict[str, Any],
    source_username: str,
    source_name: str = "",
) -> list[dict[str, Any]]:
    includes = data.get("includes") if isinstance(data.get("includes"), dict) else {}
    users = {
        str(item.get("id")): item
        for item in includes.get("users", []) or []
        if isinstance(item, dict)
    }
    tweets = {
        str(item.get("id")): item
        for item in includes.get("tweets", []) or []
        if isinstance(item, dict)
    }
    media_by_key = {
        str(item.get("media_key")): item
        for item in includes.get("media", []) or []
        if isinstance(item, dict)
    }

    result: list[dict[str, Any]] = []
    for source in data.get("data", []) or []:
        if not isinstance(source, dict) or source.get("possibly_sensitive"):
            continue

        display = source
        is_retweet = False
        for reference in source.get("referenced_tweets", []) or []:
            if not isinstance(reference, dict) or reference.get("type") != "retweeted":
                continue
            original = tweets.get(str(reference.get("id") or ""))
            if isinstance(original, dict) and not original.get("possibly_sensitive"):
                display = original
                is_retweet = True
            break

        user = users.get(str(display.get("author_id") or "")) or {}
        username = str(user.get("username") or source_username).strip()
        fallback_name = source_name if username.lower() == source_username.lower() else username
        media_items: list[dict[str, Any]] = []
        attachments = display.get("attachments") if isinstance(display.get("attachments"), dict) else {}
        for key in attachments.get("media_keys", []) or []:
            normalized = normalize_media(media_by_key.get(str(key)) or {})
            if normalized:
                media_items.append(normalized)

        post_id = str(display.get("id") or source.get("id") or "")
        source_id = str(source.get("id") or post_id)
        if not post_id:
            continue
        result.append(
            {
                "id": post_id,
                "source_id": source_id,
                "text": clean_text(str(display.get("text") or "")),
                "created_at": str(display.get("created_at") or source.get("created_at") or ""),
                "username": username,
                "name": str(user.get("name") or fallback_name),
                "profile_image_url": str(user.get("profile_image_url") or ""),
                "url": f"https://x.com/{username}/status/{post_id}",
                "is_retweet": is_retweet,
                "retweeted_by": source_username if is_retweet else "",
                "media": media_items,
            }
        )
    return result


def merge_candidates(state: dict[str, Any], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old_items = state.get("candidates") if isinstance(state.get("candidates"), list) else []
    merged: dict[str, dict[str, Any]] = {}
    for item in [*new_items, *old_items]:
        if isinstance(item, dict) and item.get("id") and str(item["id"]) not in merged:
            merged[str(item["id"])] = item

    def order(item: dict[str, Any]) -> tuple[str, int]:
        return str(item.get("created_at") or ""), int(str(item.get("source_id") or item.get("id") or "0"))

    candidates = sorted(merged.values(), key=order, reverse=True)[:50]
    state["candidates"] = candidates
    return candidates


def choose_candidate(
    candidates: list[dict[str, Any]],
    deliveries: dict[str, list[str]],
    group_ids: list[int | str],
) -> dict[str, Any] | None:
    wanted = {str(group_id) for group_id in group_ids}
    for item in candidates:
        delivered = set(deliveries.get(str(item.get("id") or ""), []))
        if delivered and delivered != wanted:
            return item
    for item in candidates:
        if not deliveries.get(str(item.get("id") or "")):
            return item
    return candidates[0] if candidates else None


def post_datetime_text(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo

            parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai"))
        except Exception:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value or "")[:16].replace("T", " ")


def build_caption(post: dict[str, Any]) -> str:
    title = "EveryOneWendell"
    author = f"{post.get('name') or post.get('username')} (@{post.get('username')})"
    if post.get("is_retweet"):
        author += f"\n由 @{post.get('retweeted_by')} 转发的原帖"
    pieces = [title, author, post_datetime_text(str(post.get("created_at") or ""))]
    if str(post.get("text") or "").strip():
        pieces.append(str(post["text"]).strip())
    pieces.append(f"原帖：{post.get('url')}")
    return "\n".join(pieces)


def download_media(item: dict[str, Any], post_id: str, index: int, max_bytes: int) -> Path:
    url = str(item.get("url") or "").strip()
    if not url:
        raise ValueError("Media URL is empty.")
    extension = ".mp4" if item.get("type") in {"video", "animated_gif"} else ".jpg"
    url_path = url.split("?", 1)[0]
    guessed = Path(url_path).suffix.lower()
    if guessed in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"}:
        extension = guessed
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    target = MEDIA_DIR / f"{post_id}_{index}_{digest}{extension}"
    if target.exists() and target.stat().st_size > 0:
        return target

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    total = 0
    with requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=90) as response:
        response.raise_for_status()
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length and content_length > max_bytes:
            raise RuntimeError(f"Media is too large ({content_length} bytes).")
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"Media exceeded {max_bytes} bytes while downloading.")
                output.write(chunk)
    temporary.replace(target)
    return target


def image_segment(path: Path) -> dict[str, Any]:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image", "data": {"file": f"base64://{encoded}"}}


def video_segment(
    path: Path,
    original_url: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    host_dir = Path(str(config.get("napcat_media_host_dir") or "/opt/napcat/data/wendell_media"))
    container_dir = str(config.get("napcat_media_container_dir") or "/app/.config/QQ/wendell_media").rstrip("/")
    try:
        host_dir.mkdir(parents=True, exist_ok=True)
        shared_path = host_dir / path.name
        if path.resolve() != shared_path.resolve():
            shutil.copy2(path, shared_path)
        return {"type": "video", "data": {"file": f"file://{container_dir}/{shared_path.name}"}}
    except (OSError, RuntimeError):
        max_base64_bytes = int(float(config.get("everyone_wendell_video_base64_max_mb") or 20) * 1024 * 1024)
        if path.stat().st_size <= max_base64_bytes:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return {"type": "video", "data": {"file": f"base64://{encoded}"}}
        return {"type": "video", "data": {"file": original_url}}


def build_message(
    caption: str,
    post: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path]]:
    message: list[dict[str, Any]] = [{"type": "text", "data": {"text": caption}}]
    downloaded: list[Path] = []
    max_bytes = int(float(config.get("everyone_wendell_media_max_mb") or 100) * 1024 * 1024)
    for index, item in enumerate(post.get("media", []) or [], 1):
        if not isinstance(item, dict):
            continue
        try:
            path = download_media(item, str(post.get("id") or "post"), index, max_bytes=max_bytes)
            downloaded.append(path)
            if item.get("type") in {"video", "animated_gif"}:
                message.append(video_segment(path, str(item.get("url") or ""), config))
            else:
                message.append(image_segment(path))
        except Exception as exc:
            print(f"Media {index} download/send preparation failed: {exc}", file=sys.stderr)
            if item.get("type") in {"video", "animated_gif"} and str(item.get("url") or "").strip():
                message.append({"type": "video", "data": {"file": str(item["url"])}})
                continue
            preview_url = str(item.get("preview_url") or "").strip()
            if preview_url:
                message.append({"type": "image", "data": {"file": preview_url}})
    return message, downloaded


def send_post_to_target(
    config: dict[str, Any],
    target_id: int | str,
    caption: str,
    message: list[dict[str, Any]],
    *,
    private: bool = False,
) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    action = "send_private_msg" if private else "send_group_msg"
    id_key = "user_id" if private else "group_id"
    result = post_onebot(
        base_url=base_url,
        action=action,
        payload={id_key: target_id, "message": message},
        access_token=str(config.get("access_token") or ""),
        timeout=180,
    )
    if result.get("_napcat_callback_timeout"):
        print(f"NapCat callback timed out for target {target_id}; native result reported success.")
    target_kind = "user" if private else "group"
    print(f"Sent EveryOneWendell to {target_kind} {target_id}.")


def clean_old_media(days: int = 14) -> None:
    if not MEDIA_DIR.exists():
        return
    cutoff = china_now().timestamp() - max(1, days) * 86400
    for path in MEDIA_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one recent @wendellindashop post to configured QQ groups.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--username", default="")
    parser.add_argument("--group-id", action="append")
    parser.add_argument("--private-user-id", default="", help="Send one preview privately without changing group delivery state.")
    parser.add_argument("--force", action="store_true", help="Send even if today's scheduled post already succeeded.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and prepare the post without sending it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    config = load_json(config_path)
    state_path = Path(str(config.get("everyone_wendell_state_path") or STATE_PATH))
    state = load_json(state_path)
    private_user_id = str(args.private_user_id or "").strip()
    group_ids = [] if private_user_id else (
        normalized_group_ids(args.group_id) if args.group_id else configured_group_ids(config)
    )
    if not private_user_id and not group_ids:
        raise ValueError("No QQ groups configured in everyone_wendell_group_ids or allowed_group_ids.")

    today = china_now().date().isoformat()
    if not private_user_id and not args.force and not args.dry_run and state.get("last_success_date") == today:
        print(f"EveryOneWendell already sent successfully on {today}.")
        return 0

    username = str(args.username or config.get("everyone_wendell_username") or DEFAULT_USERNAME).strip().lstrip("@")
    bearer_token = str(config.get("x_bearer_token") or "")
    if not normalize_bearer_token(bearer_token):
        raise ValueError("x_bearer_token is not configured.")

    fetch_error = ""
    try:
        author = resolve_author(bearer_token, username, state)
        data = fetch_author_posts(
            bearer_token,
            author_id=author["id"],
            since_id=str(state.get("latest_source_id") or ""),
            fetch_limit=int(config.get("everyone_wendell_fetch_limit") or 5),
        )
        new_items = normalize_candidates(
            data,
            source_username=author.get("username") or username,
            source_name=author.get("name") or username,
        )
        if data.get("data"):
            source_ids = [str(item.get("id") or "") for item in data.get("data", []) if isinstance(item, dict)]
            numeric_ids = [item for item in source_ids if item.isdigit()]
            if numeric_ids:
                state["latest_source_id"] = max(numeric_ids, key=int)
        candidates = merge_candidates(state, new_items)
    except Exception as exc:
        fetch_error = str(exc)
        print(f"X refresh failed, trying cached posts: {exc}", file=sys.stderr)
        candidates = merge_candidates(state, [])

    deliveries = state.get("deliveries") if isinstance(state.get("deliveries"), dict) else {}
    deliveries = {
        str(key): [str(group_id) for group_id in value]
        for key, value in deliveries.items()
        if isinstance(value, list)
    }
    post = candidates[0] if private_user_id and candidates else choose_candidate(candidates, deliveries, group_ids)
    if not post:
        raise RuntimeError(fetch_error or "No recent X posts are available.")

    post_id = str(post.get("id") or "")
    expected_groups = {str(group_id) for group_id in group_ids}
    delivered_groups = set(deliveries.get(post_id, []))
    if delivered_groups >= expected_groups:
        delivered_groups = set()

    caption = build_caption(post)
    message, downloaded = build_message(caption, post, config)
    print(caption)
    target_description = f"private={private_user_id}" if private_user_id else f"groups={','.join(map(str, group_ids))}"
    print(f"media={len(downloaded)} {target_description}")
    if args.dry_run:
        save_json(state_path, state)
        return 0

    if private_user_id:
        send_post_to_target(config, private_user_id, caption, message, private=True)
        save_json(state_path, state)
        clean_old_media(days=int(config.get("everyone_wendell_media_keep_days") or 14))
        return 0

    failures: list[str] = []
    for group_id in group_ids:
        group_key = str(group_id)
        if group_key in delivered_groups:
            continue
        try:
            send_post_to_target(config, group_id, caption, message)
            delivered_groups.add(group_key)
            deliveries[post_id] = sorted(delivered_groups)
            state["deliveries"] = deliveries
            save_json(state_path, state)
        except Exception as exc:
            failures.append(f"{group_id}: {exc}")
            print(f"Failed to send group {group_id}: {exc}", file=sys.stderr)

    if delivered_groups >= expected_groups:
        state["last_success_date"] = today
        state["last_sent_post_id"] = post_id
        state["last_sent_at"] = china_now().isoformat()
    state["deliveries"] = dict(list(deliveries.items())[-100:])
    save_json(state_path, state)
    clean_old_media(days=int(config.get("everyone_wendell_media_keep_days") or 14))

    if failures:
        raise RuntimeError("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
