from __future__ import annotations

import html
import json
import math
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_JSON = BASE_DIR / "reddit_pets.json"
OUTPUT_IMAGE = BASE_DIR / "reddit_pets.jpg"
CACHE_DIR = BASE_DIR / ".cache" / "reddit_pet_images"
LOG_DIR = BASE_DIR / "logs"
DEBUG_LOG = LOG_DIR / "reddit_pets_debug.log"

USER_AGENT = "FortniteDailyShopQQBot/1.0 (Reddit pet digest; contact: local-user)"
SUBREDDITS = (
    "aww",
    "cats",
    "CatPics",
    "kittens",
    "dog",
    "dogpictures",
    "puppies",
    "rarepuppers",
    "foxes",
    "FoxPics",
    "wolves",
    "wolfdogs",
    "AnimalsBeingBros",
)
SORTS = (("hot", ""), ("top", "day"))
REDDIT_ENDPOINTS = (
    "https://www.reddit.com/r/{subreddit}/{sort}.json",
    "https://old.reddit.com/r/{subreddit}/{sort}.json",
    "https://api.reddit.com/r/{subreddit}/{sort}",
)
PET_KEYWORDS = (
    "cat",
    "cats",
    "kitten",
    "dog",
    "dogs",
    "puppy",
    "fox",
    "foxes",
    "wolf",
    "wolves",
    "pet",
    "animal",
)

WIDTH = 1080
PADDING = 34
GAP = 18
CARD_HEIGHT = 230
IMAGE_SIZE = 190
HEADER_HEIGHT = 150
FOOTER_HEIGHT = 64

BG_TOP = (8, 21, 39)
BG_BOTTOM = (3, 9, 22)
CARD_BG = (12, 38, 63)
CARD_BG_2 = (8, 27, 48)
TEXT = (244, 249, 255)
MUTED = (165, 195, 224)
CYAN = (55, 205, 255)
YELLOW = (255, 215, 88)


def debug_log(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with DEBUG_LOG.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")
    except Exception:
        return


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(48, bold=True)
FONT_SUBTITLE = load_font(19)
FONT_CARD_TITLE = load_font(25, bold=True)
FONT_META = load_font(18, bold=True)
FONT_SMALL = load_font(15)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def make_gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (width, height), top)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    words = re.split(r"(\s+)", text.strip())
    lines: list[str] = []
    current = ""
    for word in words:
        attempt = f"{current}{word}"
        if text_size(draw, attempt.strip(), font)[0] <= max_width:
            current = attempt
            continue
        if current.strip():
            lines.append(current.strip())
        current = word.strip()
        if len(lines) >= max_lines:
            break
    if current.strip() and len(lines) < max_lines:
        lines.append(current.strip())

    if len(lines) == max_lines:
        while lines[-1] and text_size(draw, f"{lines[-1]}...", font)[0] > max_width:
            lines[-1] = lines[-1][:-1]
        if lines[-1]:
            lines[-1] += "..."
    return lines or [""]


def safe_title(value: Any) -> str:
    title = html.unescape(str(value or "")).replace("\n", " ").strip()
    return re.sub(r"\s+", " ", title)


def is_image_url(url: str) -> bool:
    clean = url.lower().split("?", 1)[0]
    return clean.endswith((".jpg", ".jpeg", ".png", ".webp"))


def clean_image_url(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    return html.unescape(url).replace("&amp;", "&")


def preview_image(data: dict[str, Any]) -> str:
    preview = data.get("preview")
    if not isinstance(preview, dict):
        return ""
    images = preview.get("images")
    if not isinstance(images, list) or not images:
        return ""
    first = images[0] if isinstance(images[0], dict) else {}
    source = first.get("source") if isinstance(first.get("source"), dict) else {}
    source_url = clean_image_url(source.get("url"))
    if source_url:
        return source_url

    resolutions = first.get("resolutions")
    if isinstance(resolutions, list) and resolutions:
        candidate = resolutions[-1] if isinstance(resolutions[-1], dict) else {}
        return clean_image_url(candidate.get("url"))
    return ""


def gallery_image(data: dict[str, Any]) -> str:
    gallery_data = data.get("gallery_data")
    media_metadata = data.get("media_metadata")
    if not isinstance(gallery_data, dict) or not isinstance(media_metadata, dict):
        return ""

    items = gallery_data.get("items")
    if not isinstance(items, list) or not items:
        return ""

    media_id = items[0].get("media_id") if isinstance(items[0], dict) else ""
    media = media_metadata.get(media_id)
    if not isinstance(media, dict):
        return ""

    source = media.get("s") if isinstance(media.get("s"), dict) else {}
    source_url = clean_image_url(source.get("u") or source.get("gif"))
    if source_url:
        return source_url

    previews = media.get("p")
    if isinstance(previews, list) and previews:
        candidate = previews[-1] if isinstance(previews[-1], dict) else {}
        return clean_image_url(candidate.get("u"))
    return ""


def extract_image_url(data: dict[str, Any]) -> str:
    direct = clean_image_url(data.get("url_overridden_by_dest") or data.get("url"))
    if is_image_url(direct):
        return direct

    thumbnail = clean_image_url(data.get("thumbnail"))
    if thumbnail.startswith("http") and thumbnail not in {"self", "default", "nsfw"}:
        if is_image_url(thumbnail) or "thumbs.redditmedia.com" in thumbnail or "preview.redd.it" in thumbnail:
            return thumbnail

    for candidate in (gallery_image(data), preview_image(data), direct):
        if candidate:
            return candidate
    return ""


def fetch_listing(subreddit: str, sort: str, timeframe: str = "", limit: int = 25) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit, "raw_json": 1}
    if timeframe:
        params["t"] = timeframe

    errors: list[str] = []
    payload: dict[str, Any] | None = None
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "User-Agent": USER_AGENT,
    }
    for endpoint in REDDIT_ENDPOINTS:
        url = endpoint.format(subreddit=subreddit, sort=sort)
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code in {403, 429}:
                errors.append(f"{url} HTTP {response.status_code}: {response.text[:120]!r}")
                continue
            response.raise_for_status()
            payload = response.json()
            break
        except Exception as exc:
            errors.append(f"{url} {type(exc).__name__}: {exc}")

    if payload is None:
        debug_log(f"listing failed r/{subreddit} {sort} {timeframe or '-'} | " + " | ".join(errors))
        return []

    children = payload.get("data", {}).get("children", [])
    if not isinstance(children, list):
        debug_log(f"listing had no children r/{subreddit} {sort} {timeframe or '-'}")
        return []

    posts: list[dict[str, Any]] = []
    for child in children:
        data = child.get("data") if isinstance(child, dict) else None
        if isinstance(data, dict):
            posts.append(data)
    return posts


def normalize_post(data: dict[str, Any]) -> dict[str, Any] | None:
    if data.get("over_18") or data.get("stickied"):
        return None

    image_url = extract_image_url(data)
    if not image_url:
        return None

    title = safe_title(data.get("title"))
    if not title:
        return None

    subreddit = str(data.get("subreddit") or "").strip()
    score = int(data.get("score") or 0)
    comments = int(data.get("num_comments") or 0)
    created_utc = float(data.get("created_utc") or 0)
    permalink = str(data.get("permalink") or "")
    url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink

    return {
        "id": str(data.get("id") or url or title),
        "title": title,
        "subreddit": subreddit,
        "score": score,
        "comments": comments,
        "created_utc": created_utc,
        "image_url": image_url,
        "url": url,
        "hot_score": score + comments * 5 + max(0, int(time.time() - created_utc)) * -0.00002,
    }


def fetch_pet_posts(limit: int = 5) -> list[dict[str, Any]]:
    seen: set[str] = set()
    posts: list[dict[str, Any]] = []
    listing_count = 0
    normalized_count = 0
    no_image_count = 0
    for subreddit in SUBREDDITS:
        for sort, timeframe in SORTS:
            listing = fetch_listing(subreddit, sort, timeframe=timeframe, limit=35)
            listing_count += len(listing)

            for raw in listing:
                post = normalize_post(raw)
                if not post:
                    if raw.get("over_18") or raw.get("stickied"):
                        continue
                    if not extract_image_url(raw):
                        no_image_count += 1
                    continue
                normalized_count += 1
                if post["id"] in seen:
                    continue
                seen.add(post["id"])
                posts.append(post)

    posts.sort(key=lambda item: float(item.get("hot_score") or 0), reverse=True)
    debug_log(
        f"fetch summary listings={listing_count} normalized={normalized_count} "
        f"images_missing={no_image_count} selected={len(posts[:limit])}"
    )
    return posts[:limit]


def download_image(url: str) -> Image.Image | None:
    if not url:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-90:] + ".img"
    cached = CACHE_DIR / filename
    try:
        if cached.exists():
            return ImageOps.exif_transpose(Image.open(cached)).convert("RGB")

        response = requests.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.reddit.com/"}, timeout=30)
        response.raise_for_status()
        cached.write_bytes(response.content)
        return ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGB")
    except Exception:
        return None


def paste_cover(base: Image.Image, source: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    image = source.copy().convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    x = (resized.width - width) // 2
    y = (resized.height - height) // 2
    cropped = resized.crop((x, y, x + width, y + height))
    mask = rounded_mask((width, height), radius)
    base.paste(cropped, (left, top), mask)


def render_pet_image(posts: list[dict[str, Any]], output: Path = OUTPUT_IMAGE) -> Path:
    rows = max(1, len(posts))
    height = PADDING * 2 + HEADER_HEIGHT + rows * CARD_HEIGHT + max(0, rows - 1) * GAP + FOOTER_HEIGHT
    image = make_gradient(WIDTH, height, BG_TOP, BG_BOTTOM).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")

    for offset in range(-WIDTH, height, 90):
        draw.line((0, offset, WIDTH, offset + WIDTH), fill=(255, 255, 255, 13), width=2)

    draw.text((PADDING, PADDING + 10), "Reddit 宠物热点", fill=TEXT, font=FONT_TITLE)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    draw.text((PADDING, PADDING + 76), f"猫猫 / 狗狗 / 狐狸 / 狼 · {updated}", fill=MUTED, font=FONT_SUBTITLE)
    draw.text((PADDING, PADDING + 105), "按热度挑选图片帖，原帖链接会随消息一起发送", fill=(124, 164, 198), font=FONT_SMALL)

    y = PADDING + HEADER_HEIGHT
    for index, post in enumerate(posts, 1):
        card = (PADDING, y, WIDTH - PADDING, y + CARD_HEIGHT)
        draw.rounded_rectangle((card[0] + 5, card[1] + 7, card[2] + 5, card[3] + 7), radius=18, fill=(0, 0, 0, 96))
        panel = make_gradient(card[2] - card[0], card[3] - card[1], CARD_BG, CARD_BG_2)
        image.paste(panel, (card[0], card[1]), rounded_mask((card[2] - card[0], card[3] - card[1]), 18))
        draw.rounded_rectangle(card, radius=18, outline=(73, 185, 236), width=2)

        image_box = (PADDING + 18, y + 20, PADDING + 18 + IMAGE_SIZE, y + 20 + IMAGE_SIZE)
        pet_image = download_image(str(post.get("image_url") or ""))
        if pet_image:
            paste_cover(image, pet_image, image_box, 14)
        else:
            draw.rounded_rectangle(image_box, radius=14, fill=(18, 53, 82))
            draw.text((image_box[0] + 46, image_box[1] + 82), "NO IMAGE", fill=MUTED, font=FONT_META)

        text_x = image_box[2] + 22
        text_width = WIDTH - PADDING - text_x - 18
        badge = f"#{index}  r/{post.get('subreddit')}"
        badge_width, badge_height = text_size(draw, badge, FONT_META)
        draw.rounded_rectangle((text_x, y + 22, text_x + badge_width + 24, y + 22 + badge_height + 15), radius=10, fill=(14, 94, 132))
        draw.text((text_x + 12, y + 30), badge, fill=TEXT, font=FONT_META)

        title_lines = wrap_text(draw, str(post.get("title") or ""), FONT_CARD_TITLE, text_width, 3)
        title_y = y + 72
        for line in title_lines:
            draw.text((text_x, title_y), line, fill=TEXT, font=FONT_CARD_TITLE)
            title_y += 32

        meta = f"{int(post.get('score') or 0):,} 分 · {int(post.get('comments') or 0):,} 条评论"
        draw.text((text_x, y + CARD_HEIGHT - 52), meta, fill=YELLOW, font=FONT_META)
        y += CARD_HEIGHT + GAP

    footer = "内容来自 Reddit 公开热门帖，仅展示短标题和来源链接"
    footer_width, _ = text_size(draw, footer, FONT_SMALL)
    draw.text(((WIDTH - footer_width) // 2, height - 42), footer, fill=(118, 152, 184), font=FONT_SMALL)

    image.save(output, quality=82, optimize=True)
    return output


def caption_for_posts(posts: list[dict[str, Any]]) -> str:
    lines = ["Reddit 宠物热点"]
    for index, post in enumerate(posts[:5], 1):
        title = str(post.get("title") or "")
        if len(title) > 42:
            title = title[:39] + "..."
        lines.append(f"{index}. r/{post.get('subreddit')} · {title}")
        lines.append(str(post.get("url") or ""))
    return "\n".join(lines)


def build_reddit_pet_update(limit: int = 5) -> tuple[str, Path, list[dict[str, Any]]]:
    posts = fetch_pet_posts(limit=limit)
    if not posts:
        debug_log("no posts selected; Reddit may be unreachable from this server or returned no image posts")
    OUTPUT_JSON.write_text(
        json.dumps({"updatedAt": datetime.now(timezone.utc).isoformat(), "posts": posts}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    render_pet_image(posts)
    return caption_for_posts(posts), OUTPUT_IMAGE, posts


def main() -> int:
    caption, image_path, posts = build_reddit_pet_update()
    print(caption)
    print(f"Saved {len(posts)} posts to {OUTPUT_JSON.name}")
    print(f"Saved image to {image_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
