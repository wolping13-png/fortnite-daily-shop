from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

import requests
from PIL import Image, ImageDraw

from send_qq_shop import normalize_base_url, post_onebot
from x_posts import (
    clean_text,
    download_image,
    fit_text,
    load_font,
    normalize_bearer_token,
    paste_circle,
    paste_rounded_contain,
    text_size,
    wrap_text,
    x_user_get,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"
CACHE_DIR = BASE_DIR / ".cache" / "everyday_one_wendell"
LEGACY_CACHE_DIR = BASE_DIR / ".cache" / "everyone_wendell"
STATE_PATH = CACHE_DIR / "state.json"
LEGACY_STATE_PATH = LEGACY_CACHE_DIR / "state.json"
MEDIA_DIR = CACHE_DIR / "media"
X_USER_BY_USERNAME_URL = "https://api.x.com/2/users/by/username/{username}"
X_USERS_BY_USERNAMES_URL = "https://api.x.com/2/users/by"
X_SEARCH_RECENT_URL = "https://api.x.com/2/tweets/search/recent"
X_USER_POSTS_URL = "https://api.x.com/2/users/{user_id}/tweets"
DEFAULT_USERNAME = "wendellindashop"
DEFAULT_USER_ID = "1837315425178136576"
DEFAULT_DISPLAY_NAME = "Days without Wendell in the shop"
CARD_WIDTH = 900
CARD_BG = (0, 0, 0)
CARD_BORDER = (47, 51, 54)
CARD_TEXT = (231, 233, 234)
CARD_MUTED = (113, 118, 123)
CARD_LINK = (29, 155, 240)
CARD_FONT_TITLE = load_font(27, bold=True)
CARD_FONT_NAME = load_font(25, bold=True)
CARD_FONT_HANDLE = load_font(20)
CARD_FONT_BODY = load_font(27)
CARD_FONT_META = load_font(18)


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
        config.get("everyday_one_wendell_group_ids")
        or config.get("everyone_wendell_group_ids")
        or config.get("allowed_group_ids")
        or config.get("group_ids")
    )


def feature_config(config: dict[str, Any], name: str, default: Any) -> Any:
    current_key = f"everyday_one_wendell_{name}"
    legacy_key = f"everyone_wendell_{name}"
    if current_key in config:
        return config[current_key]
    if legacy_key in config:
        return config[legacy_key]
    return default


def x_get(url: str, bearer_token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    response: requests.Response | None = None
    retry_delays = (0, 2, 5, 10)
    for attempt, delay in enumerate(retry_delays, 1):
        if delay:
            print(f"X API is temporarily unavailable; retrying in {delay} seconds ({attempt}/{len(retry_delays)}).")
            time.sleep(delay)
        try:
            response = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {normalize_bearer_token(bearer_token)}",
                    "User-Agent": "EveryDayOneWendell/1.0",
                },
                params=params or {},
                timeout=35,
            )
        except requests.RequestException:
            if attempt < len(retry_delays):
                continue
            raise
        if response.status_code not in {500, 502, 503, 504} or attempt == len(retry_delays):
            break

    if response is None:
        raise RuntimeError("X API request did not return a response.")
    if response.status_code in {401, 403}:
        raise RuntimeError(f"X API token has no access: {response.text[:500]}")
    if response.status_code == 429:
        raise RuntimeError("X API rate limit or credits are exhausted.")
    if response.status_code in {500, 502, 503, 504}:
        raise RuntimeError(f"X API remained unavailable after retries ({response.status_code}).")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("X API returned an unexpected response.")
    return data


def x_get_with_available_auth(
    url: str,
    bearer_token: str,
    params: dict[str, str] | None = None,
    *,
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    oauth_configured = bool(
        config
        and (
            str(config.get("x_user_access_token") or "").strip()
            or (
                str(config.get("x_client_id") or "").strip()
                and str(config.get("x_user_refresh_token") or "").strip()
            )
        )
    )
    if oauth_configured and config is not None:
        try:
            return x_user_get(config, config_path, url, params or {})
        except Exception as exc:
            errors.append(f"OAuth user token: {exc}")
            print(f"X OAuth request failed; trying Bearer Token: {exc}", file=sys.stderr)

    try:
        return x_get(url, bearer_token, params)
    except Exception as exc:
        errors.append(f"Bearer Token: {exc}")
        raise RuntimeError("; ".join(errors)) from exc


def resolve_author(
    bearer_token: str,
    username: str,
    state: dict[str, Any],
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, str]:
    cached = state.get("author") if isinstance(state.get("author"), dict) else {}
    if str(cached.get("username") or "").lower() == username.lower() and cached.get("id"):
        return {key: str(cached.get(key) or "") for key in ("id", "username", "name", "profile_image_url")}

    configured_user_id = ""
    if config is not None:
        default_user_id = DEFAULT_USER_ID if username.lower() == DEFAULT_USERNAME else ""
        configured_user_id = str(feature_config(config, "user_id", default_user_id) or "").strip()
    if configured_user_id:
        author = {
            "id": configured_user_id,
            "username": username,
            "name": DEFAULT_DISPLAY_NAME if username.lower() == DEFAULT_USERNAME else username,
            "profile_image_url": "",
        }
        state["author"] = author
        return author

    fields = {"user.fields": "name,username,profile_image_url"}
    lookup_errors: list[str] = []
    user: dict[str, Any] = {}
    try:
        data = x_get_with_available_auth(
            X_USER_BY_USERNAME_URL.format(username=quote(username.lstrip("@"))),
            bearer_token,
            fields,
            config=config,
            config_path=config_path,
        )
        user = data.get("data") if isinstance(data.get("data"), dict) else {}
    except Exception as exc:
        lookup_errors.append(f"single lookup: {exc}")

    if not user.get("id"):
        try:
            data = x_get_with_available_auth(
                X_USERS_BY_USERNAMES_URL,
                bearer_token,
                {"usernames": username, **fields},
                config=config,
                config_path=config_path,
            )
            users = data.get("data") if isinstance(data.get("data"), list) else []
            user = users[0] if users and isinstance(users[0], dict) else {}
        except Exception as exc:
            lookup_errors.append(f"batch lookup: {exc}")

    if not user.get("id"):
        try:
            data = x_get_with_available_auth(
                X_SEARCH_RECENT_URL,
                bearer_token,
                {
                    "query": f"from:{username}",
                    "max_results": "10",
                    "tweet.fields": "author_id",
                    "expansions": "author_id",
                    "user.fields": "name,username,profile_image_url",
                },
                config=config,
                config_path=config_path,
            )
            included = data.get("includes") if isinstance(data.get("includes"), dict) else {}
            users = included.get("users") if isinstance(included.get("users"), list) else []
            matching = [
                item
                for item in users
                if isinstance(item, dict)
                and str(item.get("username") or "").lower() == username.lower()
            ]
            if matching:
                user = matching[0]
            else:
                posts = data.get("data") if isinstance(data.get("data"), list) else []
                author_id = str(posts[0].get("author_id") or "") if posts and isinstance(posts[0], dict) else ""
                if author_id:
                    user = {"id": author_id, "username": username, "name": username}
        except Exception as exc:
            lookup_errors.append(f"recent search fallback: {exc}")

    if not user.get("id"):
        detail = "; ".join(lookup_errors) or "no user data returned"
        raise RuntimeError(f"Could not find X author @{username}: {detail}")
    author = {key: str(user.get(key) or "") for key in ("id", "username", "name", "profile_image_url")}
    state["author"] = author
    return author


def fetch_author_posts(
    bearer_token: str,
    author_id: str,
    since_id: str = "",
    fetch_limit: int = 5,
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
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
    return x_get_with_available_auth(
        X_USER_POSTS_URL.format(user_id=author_id),
        bearer_token,
        params,
        config=config,
        config_path=config_path,
    )


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


class RssDescriptionParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.text_parts: list[str] = []
        self.media: list[dict[str, Any]] = []
        self.current_video_type = "video"
        self.current_video_poster = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        attribute_names = {str(key).lower() for key, _value in attrs}
        if tag.lower() == "br":
            self.text_parts.append("\n")
        elif tag.lower() == "video":
            self.current_video_type = (
                "animated_gif" if {"autoplay", "muted", "loop"}.issubset(attribute_names) else "video"
            )
            self.current_video_poster = urljoin(self.base_url, values.get("poster", "")) if values.get("poster") else ""
        elif tag.lower() == "img" and values.get("src"):
            self.media.append(
                {
                    "type": "photo",
                    "url": urljoin(self.base_url, values["src"]),
                    "preview_url": urljoin(self.base_url, values["src"]),
                }
            )
        elif tag.lower() == "source" and values.get("src"):
            self.media.append(
                {
                    "type": self.current_video_type,
                    "url": urljoin(self.base_url, values["src"]),
                    "preview_url": self.current_video_poster,
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div"}:
            self.text_parts.append("\n")
        elif tag.lower() == "video":
            self.current_video_type = "video"
            self.current_video_poster = ""

    def handle_data(self, data: str) -> None:
        self.text_parts.append(str(data or ""))

    def parsed_text(self) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(self.text_parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def parsed_media(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in self.media:
            url = str(item.get("url") or "")
            if url and url not in seen:
                seen.add(url)
                result.append(item)
        return result


def rss_datetime(value: str) -> str:
    try:
        parsed = parsedate_to_datetime(str(value or ""))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return str(value or "")


def x_url_from_rss_link(link: str, fallback_username: str, post_id: str) -> tuple[str, str]:
    parsed = urlparse(str(link or ""))
    parts = [part for part in parsed.path.split("/") if part]
    username = fallback_username
    if len(parts) >= 3 and parts[1] == "status":
        username = parts[0]
        post_id = parts[2]
    return username, f"https://x.com/{username}/status/{post_id}"


def fetch_public_rss_posts(
    username: str,
    config: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    configured = feature_config(config, "rss_urls", ["https://nitter.net"])
    if isinstance(configured, str):
        rss_bases = [configured]
    else:
        rss_bases = [str(item) for item in configured if str(item).strip()] if isinstance(configured, list) else []
    if not rss_bases:
        rss_bases = ["https://nitter.net"]

    errors: list[str] = []
    for base in rss_bases:
        base = base.rstrip("/")
        rss_url = f"{base}/{quote(username)}/rss"
        try:
            response = requests.get(
                rss_url,
                headers={"User-Agent": "Mozilla/5.0 EveryDayOneWendell/1.0"},
                timeout=35,
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except Exception as exc:
            errors.append(f"{rss_url}: {exc}")
            continue

        channel = root.find("./channel")
        channel_avatar = ""
        channel_name = DEFAULT_DISPLAY_NAME if username.lower() == DEFAULT_USERNAME else username
        if channel is not None:
            channel_avatar = str(channel.findtext("image/url") or "").strip()
            channel_title = str(channel.findtext("title") or "").strip()
            if " / @" in channel_title:
                channel_name = channel_title.split(" / @", 1)[0].strip() or channel_name

        result: list[dict[str, Any]] = []
        for item in root.findall(".//item")[: max(1, min(int(limit or 20), 50))]:
            post_id = str(item.findtext("guid") or "").strip()
            link = str(item.findtext("link") or "").strip()
            if not post_id:
                parsed_parts = [part for part in urlparse(link).path.split("/") if part]
                if len(parsed_parts) >= 3 and parsed_parts[1] == "status":
                    post_id = parsed_parts[2]
            if not post_id:
                continue

            creator = str(
                item.findtext("{http://purl.org/dc/elements/1.1/}creator") or f"@{username}"
            ).strip().lstrip("@")
            title = str(item.findtext("title") or "").strip()
            is_retweet = title.lower().startswith(f"rt by @{username.lower()}:")
            description = str(item.findtext("description") or "")
            parser = RssDescriptionParser(base + "/")
            parser.feed(description)
            text = parser.parsed_text()
            display_username, x_url = x_url_from_rss_link(link, creator or username, post_id)
            result.append(
                {
                    "id": post_id,
                    "source_id": post_id,
                    "text": text or re.sub(rf"^RT by @{re.escape(username)}:\s*", "", title, flags=re.I),
                    "created_at": rss_datetime(str(item.findtext("pubDate") or "")),
                    "username": display_username,
                    "name": channel_name if display_username.lower() == username.lower() else display_username,
                    "profile_image_url": channel_avatar if display_username.lower() == username.lower() else "",
                    "url": x_url,
                    "is_retweet": is_retweet,
                    "retweeted_by": username if is_retweet else "",
                    "media": parser.parsed_media(),
                }
            )
        if result:
            print(f"Loaded {len(result)} recent posts from public RSS fallback.")
            return result
        errors.append(f"{rss_url}: no posts returned")

    raise RuntimeError("Public RSS fallback failed: " + "; ".join(errors))


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


def choose_private_candidate(
    candidates: list[dict[str, Any]],
    retweet_only: bool = False,
) -> dict[str, Any] | None:
    if retweet_only:
        return next((item for item in candidates if bool(item.get("is_retweet"))), None)
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


def card_safe_label(value: str) -> str:
    return "".join(
        char
        for char in str(value or "")
        if unicodedata.category(char) not in {"So", "Cs"}
        and char not in {"\ufe0e", "\ufe0f", "\u200d"}
    ).strip()


def enrich_post_profile(post: dict[str, Any]) -> None:
    if str(post.get("profile_image_url") or "").strip() and str(post.get("name") or "").strip():
        return
    username = str(post.get("username") or "").strip().lstrip("@")
    if not username:
        return
    try:
        response = requests.get(
            f"https://api.fxtwitter.com/{quote(username)}",
            headers={"User-Agent": "Mozilla/5.0 EveryDayOneWendell/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        user = payload.get("user") if isinstance(payload, dict) and isinstance(payload.get("user"), dict) else {}
        post["name"] = str(user.get("name") or post.get("name") or username)
        post["profile_image_url"] = str(user.get("avatar_url") or post.get("profile_image_url") or "")
    except Exception as exc:
        print(f"Could not enrich @{username} profile for the post card: {exc}", file=sys.stderr)


def render_post_card(post: dict[str, Any]) -> Path:
    enrich_post_profile(post)
    probe = Image.new("RGB", (CARD_WIDTH, 300), CARD_BG)
    probe_draw = ImageDraw.Draw(probe)
    body_width = CARD_WIDTH - 64
    body_lines = wrap_text(probe_draw, str(post.get("text") or ""), CARD_FONT_BODY, body_width, 80)
    body_height = max(38, len(body_lines) * 39)
    media_item = next(
        (item for item in post.get("media", []) or [] if isinstance(item, dict)),
        {},
    )
    preview_url = str(
        media_item.get("preview_url")
        or (media_item.get("url") if media_item.get("type") == "photo" else "")
        or ""
    )
    media_preview = download_image(preview_url) if preview_url else None
    media_height = 0
    if media_preview is not None:
        ratio = media_preview.height / max(1, media_preview.width)
        if ratio >= 1.5:
            media_height = 720
        elif ratio >= 1.05:
            media_height = 610
        elif ratio >= 0.72:
            media_height = 520
        else:
            media_height = 450
    retweet_height = 38 if post.get("is_retweet") else 0
    header_height = 66
    author_height = 86
    footer_height = 62
    media_block_height = media_height + 24 if media_height else 0
    card_height = header_height + retweet_height + author_height + body_height + media_block_height + footer_height + 32

    image = Image.new("RGB", (CARD_WIDTH, card_height), CARD_BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, CARD_WIDTH - 1, card_height - 1), outline=CARD_BORDER, width=1)

    draw.text((32, 20), "EveryDayOneWendell", fill=CARD_TEXT, font=CARD_FONT_TITLE)
    x_mark = "X"
    x_width, _ = text_size(draw, x_mark, CARD_FONT_TITLE)
    draw.text((CARD_WIDTH - 32 - x_width, 20), x_mark, fill=CARD_TEXT, font=CARD_FONT_TITLE)
    draw.line((0, header_height, CARD_WIDTH, header_height), fill=CARD_BORDER, width=1)

    y = header_height + 16
    if post.get("is_retweet"):
        draw.text(
            (44, y),
            f"@{post.get('retweeted_by') or DEFAULT_USERNAME} 转发",
            fill=CARD_MUTED,
            font=CARD_FONT_META,
        )
        y += retweet_height

    avatar_size = 62
    avatar_x = 32
    avatar_y = y
    avatar = download_image(str(post.get("profile_image_url") or ""))
    if avatar is not None:
        paste_circle(image, avatar, avatar_x, avatar_y, avatar_size)
    else:
        draw.ellipse(
            (avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size),
            fill=(32, 35, 39),
        )
        initial = (str(post.get("name") or post.get("username") or "X").strip()[:1] or "X").upper()
        iw, ih = text_size(draw, initial, CARD_FONT_NAME)
        draw.text(
            (avatar_x + (avatar_size - iw) // 2, avatar_y + (avatar_size - ih) // 2 - 2),
            initial,
            fill=CARD_TEXT,
            font=CARD_FONT_NAME,
        )

    author_x = avatar_x + avatar_size + 14
    available_width = CARD_WIDTH - author_x - 32
    name = fit_text(
        draw,
        card_safe_label(str(post.get("name") or post.get("username") or "")),
        CARD_FONT_NAME,
        available_width,
    )
    draw.text((author_x, y + 2), name, fill=CARD_TEXT, font=CARD_FONT_NAME)
    handle = fit_text(draw, f"@{post.get('username') or ''}", CARD_FONT_HANDLE, available_width)
    draw.text((author_x, y + 39), handle, fill=CARD_MUTED, font=CARD_FONT_HANDLE)
    y += author_height

    for index, line in enumerate(body_lines or [""]):
        draw.text((32, y + index * 39), line, fill=CARD_TEXT, font=CARD_FONT_BODY)
    y += body_height + 20

    if media_preview is not None and media_height:
        media_box = (32, y, CARD_WIDTH - 32, y + media_height)
        paste_rounded_contain(image, media_preview, media_box, radius=8)
        draw.rounded_rectangle(media_box, radius=8, outline=CARD_BORDER, width=1)
        media_type = str(media_item.get("type") or "")
        if media_type in {"animated_gif", "video"}:
            badge = "GIF" if media_type == "animated_gif" else "VIDEO"
            badge_width, badge_height = text_size(draw, badge, CARD_FONT_META)
            badge_box = (
                media_box[0] + 16,
                media_box[1] + 16,
                media_box[0] + 36 + badge_width,
                media_box[1] + 32 + badge_height,
            )
            draw.rounded_rectangle(badge_box, radius=6, fill=(15, 20, 25), outline=(90, 98, 105), width=1)
            draw.text((badge_box[0] + 10, badge_box[1] + 6), badge, fill=CARD_TEXT, font=CARD_FONT_META)
        y += media_height + 24

    created_at = post_datetime_text(str(post.get("created_at") or ""))
    draw.text((32, y), created_at, fill=CARD_MUTED, font=CARD_FONT_META)
    footer_text = "查看 X 原帖"
    footer_width, _ = text_size(draw, footer_text, CARD_FONT_META)
    draw.text((CARD_WIDTH - 32 - footer_width, y), footer_text, fill=CARD_LINK, font=CARD_FONT_META)

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    target = MEDIA_DIR / f"{post.get('id') or 'post'}_card.jpg"
    image.save(target, quality=90, optimize=True)
    return target


def build_caption(post: dict[str, Any]) -> str:
    title = "EveryDayOneWendell"
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


def ffmpeg_executable() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as exc:
        raise RuntimeError("ffmpeg is unavailable; install imageio-ffmpeg or the ffmpeg package.") from exc


def convert_mp4_to_gif(path: Path, config: dict[str, Any]) -> Path:
    target = path.with_suffix(".gif")
    if target.exists() and target.stat().st_size > 0:
        return target

    executable = ffmpeg_executable()
    max_bytes = int(float(feature_config(config, "gif_max_mb", 15) or 15) * 1024 * 1024)
    profiles = [
        (
            int(feature_config(config, "gif_fps", 12) or 12),
            int(feature_config(config, "gif_max_width", 640) or 640),
            128,
        ),
        (8, 480, 96),
    ]
    last_error = ""
    for fps, width, colors in profiles:
        target.unlink(missing_ok=True)
        video_filter = (
            f"fps={fps},scale=min(iw\\,{width}):-2:flags=lanczos,"
            f"split[s0][s1];[s0]palettegen=max_colors={colors}[p];"
            "[s1][p]paletteuse=dither=sierra2_4a"
        )
        result = subprocess.run(
            [
                executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(path),
                "-filter_complex",
                video_filter,
                "-loop",
                "0",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0 or not target.exists():
            last_error = (result.stderr or result.stdout or f"ffmpeg exited with {result.returncode}")[-1000:]
            continue
        if target.stat().st_size <= max_bytes:
            return target
        last_error = f"converted GIF is larger than {max_bytes} bytes"

    target.unlink(missing_ok=True)
    raise RuntimeError(f"Could not convert MP4 to a QQ-safe GIF: {last_error}")


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
        max_base64_bytes = int(float(feature_config(config, "video_base64_max_mb", 20) or 20) * 1024 * 1024)
        if path.stat().st_size <= max_base64_bytes:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return {"type": "video", "data": {"file": f"base64://{encoded}"}}
        return {"type": "video", "data": {"file": original_url}}


def build_message(
    caption: str,
    post: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path]]:
    downloaded: list[Path] = []
    message: list[dict[str, Any]] = [{"type": "text", "data": {"text": caption}}]
    link_segment: dict[str, Any] | None = None
    if bool(feature_config(config, "post_card_enabled", True)):
        try:
            card_path = render_post_card(post)
            downloaded.append(card_path)
            message = [image_segment(card_path)]
            link_segment = {"type": "text", "data": {"text": f"\n原帖：{post.get('url')}"}}
        except Exception as exc:
            print(f"Post card rendering failed; using text fallback: {exc}", file=sys.stderr)
    max_bytes = int(float(feature_config(config, "media_max_mb", 100) or 100) * 1024 * 1024)
    for index, item in enumerate(post.get("media", []) or [], 1):
        if not isinstance(item, dict):
            continue
        try:
            path = download_media(item, str(post.get("id") or "post"), index, max_bytes=max_bytes)
            downloaded.append(path)
            if item.get("type") == "animated_gif":
                try:
                    gif_path = convert_mp4_to_gif(path, config)
                    downloaded.append(gif_path)
                    message.append(image_segment(gif_path))
                except Exception as exc:
                    print(f"GIF conversion failed; sending MP4 fallback: {exc}", file=sys.stderr)
                    message.append(video_segment(path, str(item.get("url") or ""), config))
            elif item.get("type") == "video":
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
    if link_segment is not None:
        message.append(link_segment)
    return message, downloaded


def split_video_message_batches(message: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    video_segments = [segment for segment in message if str(segment.get("type") or "") == "video"]
    if not video_segments:
        return [message]

    regular_segments = [segment for segment in message if str(segment.get("type") or "") != "video"]
    batches: list[list[dict[str, Any]]] = []
    if regular_segments:
        batches.append(regular_segments)
    batches.extend([[segment] for segment in video_segments])
    return batches


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
    batches = split_video_message_batches(message)
    for index, batch in enumerate(batches, 1):
        result = post_onebot(
            base_url=base_url,
            action=action,
            payload={id_key: target_id, "message": batch},
            access_token=str(config.get("access_token") or ""),
            timeout=180,
        )
        if result.get("_napcat_callback_timeout"):
            print(
                f"NapCat callback timed out for target {target_id} "
                f"batch {index}/{len(batches)}; native result reported success."
            )
    target_kind = "user" if private else "group"
    print(f"Sent EveryDayOneWendell to {target_kind} {target_id} in {len(batches)} message(s).")


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
    parser.add_argument("--retweet-only", action="store_true", help="For a private preview, select the newest retweeted post.")
    parser.add_argument("--force", action="store_true", help="Send even if today's scheduled post already succeeded.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and prepare the post without sending it.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    config = load_json(config_path)
    state_path = Path(str(feature_config(config, "state_path", STATE_PATH) or STATE_PATH))
    if not state_path.exists() and state_path == STATE_PATH and LEGACY_STATE_PATH.exists():
        state = load_json(LEGACY_STATE_PATH)
        save_json(state_path, state)
    else:
        state = load_json(state_path)
    private_user_id = str(args.private_user_id or "").strip()
    group_ids = [] if private_user_id else (
        normalized_group_ids(args.group_id) if args.group_id else configured_group_ids(config)
    )
    if not private_user_id and not group_ids:
        raise ValueError("No QQ groups configured in everyday_one_wendell_group_ids or allowed_group_ids.")

    today = china_now().date().isoformat()
    if not private_user_id and not args.force and not args.dry_run and state.get("last_success_date") == today:
        print(f"EveryDayOneWendell already sent successfully on {today}.")
        return 0

    username = str(args.username or feature_config(config, "username", DEFAULT_USERNAME) or DEFAULT_USERNAME).strip().lstrip("@")
    bearer_token = str(config.get("x_bearer_token") or "")
    fetch_error = ""
    candidates: list[dict[str, Any]] = []
    prefer_rss = bool(feature_config(config, "prefer_rss", True))
    if prefer_rss:
        try:
            rss_items = fetch_public_rss_posts(
                username,
                config,
                limit=int(feature_config(config, "rss_fetch_limit", 20) or 20),
            )
            candidates = merge_candidates(state, rss_items)
        except Exception as rss_exc:
            fetch_error = str(rss_exc)
            print(f"RSS refresh failed, trying official X API: {rss_exc}", file=sys.stderr)

    if not candidates:
        try:
            author = resolve_author(
                bearer_token,
                username,
                state,
                config=config,
                config_path=config_path,
            )
            data = fetch_author_posts(
                bearer_token,
                author_id=author["id"],
                since_id=str(state.get("latest_source_id") or ""),
                fetch_limit=int(feature_config(config, "fetch_limit", 5) or 5),
                config=config,
                config_path=config_path,
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
            fetch_error = f"{fetch_error}; {exc}".strip("; ")
            print(f"Official X refresh failed: {exc}", file=sys.stderr)
            if not prefer_rss:
                try:
                    rss_items = fetch_public_rss_posts(
                        username,
                        config,
                        limit=int(feature_config(config, "rss_fetch_limit", 20) or 20),
                    )
                    candidates = merge_candidates(state, rss_items)
                except Exception as rss_exc:
                    fetch_error = f"{fetch_error}; {rss_exc}"
                    print(f"RSS fallback also failed: {rss_exc}", file=sys.stderr)
            if not candidates:
                candidates = merge_candidates(state, [])

    deliveries = state.get("deliveries") if isinstance(state.get("deliveries"), dict) else {}
    deliveries = {
        str(key): [str(group_id) for group_id in value]
        for key, value in deliveries.items()
        if isinstance(value, list)
    }
    post = (
        choose_private_candidate(candidates, retweet_only=args.retweet_only)
        if private_user_id
        else choose_candidate(candidates, deliveries, group_ids)
    )
    if not post:
        if private_user_id and args.retweet_only:
            raise RuntimeError("No recent retweeted X post is available.")
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
        clean_old_media(days=int(feature_config(config, "media_keep_days", 14) or 14))
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
    clean_old_media(days=int(feature_config(config, "media_keep_days", 14) or 14))

    if failures:
        raise RuntimeError("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
