from __future__ import annotations

import argparse
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "x_posts"
OUTPUT_PATH = BASE_DIR / "x_posts.jpg"
X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"

WIDTH = 900
PADDING = 30
CARD_GAP = 22
IMAGE_SIZE = 250
BG_TOP = (6, 17, 38)
BG_BOTTOM = (2, 8, 22)
CARD_BG = (12, 31, 64)
TEXT = (244, 248, 255)
MUTED = (178, 199, 229)
YELLOW = (255, 212, 56)


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


FONT_TITLE = load_font(34, bold=True)
FONT_NAME = load_font(23, bold=True)
FONT_TEXT = load_font(21)
FONT_META = load_font(17)
FONT_SMALL = load_font(15)


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def clean_text(text: str) -> str:
    value = re.sub(r"https?://\S+", "", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return "".join(ch for ch in value if ch.isprintable())


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    value = clean_text(text)
    if not value:
        return []

    lines: list[str] = []
    current = ""
    for char in value:
        attempt = current + char
        if text_size(draw, attempt, font)[0] <= max_width:
            current = attempt
            continue
        if current:
            lines.append(current)
        current = char.strip()
        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and text_size(draw, lines[-1], font)[0] > max_width - 20:
        while lines[-1] and text_size(draw, lines[-1] + "...", font)[0] > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "..."

    return lines[:max_lines]


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    value = clean_text(text)
    if text_size(draw, value, font)[0] <= max_width:
        return value
    while value and text_size(draw, value + "...", font)[0] > max_width:
        value = value[:-1]
    return value + "..." if value else ""


def make_gradient(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), BG_TOP)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(BG_TOP[i] * (1 - ratio) + BG_BOTTOM[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def topic_to_query(topic: str, fallback_query: str) -> str:
    if not fallback_query.strip():
        fallback_query = "(cat OR dog OR wolf OR fox OR 宠物 OR 猫 OR 狗 OR 狼 OR 狐狸) has:media -is:retweet"

    compact = re.sub(r"\s+", "", topic.strip().lower())
    if "狼" in compact or "wolf" in compact:
        return "(wolf OR wolves OR 狼 OR 狼狼) has:media -is:retweet"
    if "狐" in compact or "fox" in compact:
        return "(fox OR foxes OR 狐狸) has:media -is:retweet"
    if "猫" in compact or "cat" in compact:
        return "(cat OR cats OR 猫 OR 猫猫) has:media -is:retweet"
    if "狗" in compact or "dog" in compact:
        return "(dog OR dogs OR puppy OR 狗 OR 狗狗) has:media -is:retweet"
    if topic.strip() and not compact.startswith(("x宠物", "x热点", "x帖子")):
        value = topic.strip()
        value = re.sub(r"^(x|X|推特|twitter)\s*", "", value).strip()
        if value:
            return f"({value}) has:media -is:retweet"
    return fallback_query


def search_x_posts(
    bearer_token: str,
    query: str,
    fetch_limit: int = 30,
    timeout: int = 25,
) -> dict[str, Any]:
    token = bearer_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise ValueError("X Bearer Token has not been configured.")

    params = {
        "query": query,
        "max_results": str(max(10, min(fetch_limit, 100))),
        "sort_order": "relevancy",
        "tweet.fields": "created_at,public_metrics,author_id,possibly_sensitive,lang",
        "expansions": "author_id,attachments.media_keys",
        "media.fields": "media_key,type,url,preview_image_url,width,height",
        "user.fields": "username,name,profile_image_url",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "fortnite-daily-shop-qq-bot/1.0",
    }
    response = requests.get(X_SEARCH_URL, headers=headers, params=params, timeout=timeout)
    if response.status_code in {401, 403}:
        detail = response.text[:500]
        raise RuntimeError(f"X API 没有权限或 token 不可用：{detail}")
    if response.status_code == 429:
        raise RuntimeError("X API 请求太频繁或额度用完了。")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("X API returned an unexpected response.")
    return data


def download_image(url: str) -> Image.Image | None:
    if not url:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    cached = CACHE_DIR / f"{digest}.jpg"
    if cached.exists():
        try:
            return Image.open(cached).convert("RGB")
        except Exception:
            cached.unlink(missing_ok=True)

    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.save(cached, quality=86, optimize=True)
        return image
    except Exception:
        return None


def extract_posts(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    users = {str(item.get("id")): item for item in data.get("includes", {}).get("users", []) if isinstance(item, dict)}
    media = {
        str(item.get("media_key")): item
        for item in data.get("includes", {}).get("media", [])
        if isinstance(item, dict)
    }

    posts: list[dict[str, Any]] = []
    for tweet in data.get("data", []) or []:
        if not isinstance(tweet, dict) or tweet.get("possibly_sensitive"):
            continue

        keys = tweet.get("attachments", {}).get("media_keys", [])
        image_url = ""
        for key in keys:
            item = media.get(str(key)) or {}
            image_url = str(item.get("url") or item.get("preview_image_url") or "")
            if image_url:
                break
        if not image_url:
            continue

        user = users.get(str(tweet.get("author_id"))) or {}
        metrics = tweet.get("public_metrics") or {}
        score = (
            int(metrics.get("like_count") or 0)
            + int(metrics.get("retweet_count") or 0) * 2
            + int(metrics.get("quote_count") or 0) * 2
            + int(metrics.get("reply_count") or 0)
        )
        username = str(user.get("username") or "unknown")
        posts.append(
            {
                "id": str(tweet.get("id") or ""),
                "text": clean_text(str(tweet.get("text") or "")),
                "name": str(user.get("name") or username),
                "username": username,
                "image_url": image_url,
                "score": score,
                "likes": int(metrics.get("like_count") or 0),
                "retweets": int(metrics.get("retweet_count") or 0),
                "url": f"https://x.com/{username}/status/{tweet.get('id')}",
            }
        )

    posts.sort(key=lambda item: item.get("score", 0), reverse=True)
    return posts[:limit]


def crop_cover(source: Image.Image, width: int, height: int) -> Image.Image:
    image = source.copy()
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    x = max(0, (resized.width - width) // 2)
    y = max(0, (resized.height - height) // 2)
    return resized.crop((x, y, x + width, y + height))


def draw_post_card(base: Image.Image, draw: ImageDraw.ImageDraw, y: int, post: dict[str, Any]) -> int:
    card_height = 330
    x = PADDING
    width = WIDTH - PADDING * 2
    draw.rounded_rectangle((x, y, x + width, y + card_height), radius=18, fill=CARD_BG, outline=(255, 255, 255, 34), width=1)

    image = download_image(str(post.get("image_url") or ""))
    image_box = (x + 22, y + 48, x + 22 + IMAGE_SIZE, y + 48 + IMAGE_SIZE)
    if image is not None:
        thumb = crop_cover(image, IMAGE_SIZE, IMAGE_SIZE)
        base.paste(thumb, image_box[:2])
        draw.rounded_rectangle(image_box, radius=14, outline=(255, 255, 255, 55), width=2)

    text_x = image_box[2] + 24
    text_right = x + width - 22
    max_text_width = text_right - text_x

    title = fit_text(draw, f'{post.get("name", "")}  @{post.get("username", "")}', FONT_NAME, max_text_width)
    draw.text((text_x, y + 44), title, fill=TEXT, font=FONT_NAME)
    meta = f'热度 {post.get("score", 0)}  赞 {post.get("likes", 0)}  转 {post.get("retweets", 0)}'
    draw.text((text_x, y + 80), meta, fill=YELLOW, font=FONT_META)

    for index, line in enumerate(wrap_text(draw, str(post.get("text") or ""), FONT_TEXT, max_text_width, 5)):
        draw.text((text_x, y + 124 + index * 31), line, fill=TEXT, font=FONT_TEXT)

    link = fit_text(draw, str(post.get("url") or ""), FONT_SMALL, max_text_width)
    draw.text((text_x, y + card_height - 40), link, fill=MUTED, font=FONT_SMALL)
    return y + card_height


def render_x_posts_image(posts: list[dict[str, Any]], query: str, path: Path = OUTPUT_PATH) -> Path:
    height = PADDING * 2 + 86 + len(posts) * 330 + max(0, len(posts) - 1) * CARD_GAP + 36
    image = make_gradient(WIDTH, height).convert("RGB")
    draw = ImageDraw.Draw(image)

    draw.text((PADDING, 24), "X 热门公开帖子", fill=TEXT, font=FONT_TITLE)
    subtitle = fit_text(draw, f"Query: {query}", FONT_META, WIDTH - PADDING * 2)
    draw.text((PADDING, 68), subtitle, fill=MUTED, font=FONT_META)

    y = 112
    for post in posts:
        y = draw_post_card(image, draw, y, post) + CARD_GAP

    footer = "数据来自 X API，仅展示公开帖子和原帖链接"
    fw, _ = text_size(draw, footer, FONT_SMALL)
    draw.text(((WIDTH - fw) // 2, height - 34), footer, fill=(128, 154, 190), font=FONT_SMALL)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=84, optimize=True)
    return path


def build_x_posts_update(
    bearer_token: str,
    topic: str = "",
    limit: int = 3,
    fetch_limit: int = 30,
    fallback_query: str = "(cat OR dog OR wolf OR fox OR 宠物 OR 猫 OR 狗 OR 狼 OR 狐狸) has:media -is:retweet",
) -> tuple[str, Path, list[dict[str, Any]]]:
    query = topic_to_query(topic, fallback_query)
    data = search_x_posts(bearer_token=bearer_token, query=query, fetch_limit=fetch_limit)
    posts = extract_posts(data, limit=max(1, min(limit, 5)))
    if not posts:
        return "暂时没抓到合适的 X 图片帖子。", OUTPUT_PATH, []

    path = render_x_posts_image(posts, query=query)
    caption = f"X 热门公开帖子 · {len(posts)} 条"
    return caption, path, posts


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch public X posts and render a QQ-friendly image.")
    parser.add_argument("--config", default=str(BASE_DIR / "gemini_bot_config.json"))
    parser.add_argument("--topic", default="X宠物")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    token = str(config.get("x_bearer_token") or "")
    caption, path, posts = build_x_posts_update(
        bearer_token=token,
        topic=args.topic,
        limit=int(config.get("x_search_limit") or 3),
        fetch_limit=int(config.get("x_search_fetch_limit") or 30),
        fallback_query=str(config.get("x_search_query") or ""),
    )
    print(caption)
    print(path)
    print(f"posts={len(posts)}")
    return 0 if posts else 1


if __name__ == "__main__":
    raise SystemExit(main())
