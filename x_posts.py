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
CARD_GAP = 18
AVATAR_SIZE = 56
PAGE_BG = (0, 0, 0)
CARD_BG = (0, 0, 0)
BORDER = (47, 51, 54)
TEXT = (231, 233, 234)
MUTED = (113, 118, 123)
LINK = (29, 155, 240)


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


FONT_TITLE = load_font(30, bold=True)
FONT_NAME = load_font(22, bold=True)
FONT_HANDLE = load_font(19)
FONT_TEXT = load_font(22)
FONT_META = load_font(18)
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

    if " " in value:
        for word in [part for part in value.split(" ") if part]:
            attempt = word if not current else f"{current} {word}"
            if text_size(draw, attempt, font)[0] <= max_width:
                current = attempt
                continue
            if current:
                lines.append(current)
            current = word
            while current and text_size(draw, current, font)[0] > max_width:
                piece = current
                while piece and text_size(draw, piece, font)[0] > max_width:
                    piece = piece[:-1]
                if piece:
                    lines.append(piece)
                current = current[len(piece) :]
            if len(lines) >= max_lines:
                break
    else:
        for char in value:
            attempt = current + char
            if text_size(draw, attempt, font)[0] <= max_width:
                current = attempt
                continue
            if current:
                lines.append(current)
            current = char
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


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def paste_rounded(base: Image.Image, source: Image.Image, box: tuple[int, int, int, int], radius: int = 20) -> None:
    width = box[2] - box[0]
    height = box[3] - box[1]
    image = crop_cover(source, width, height)
    mask = rounded_mask((width, height), radius)
    base.paste(image, box[:2], mask)


def paste_circle(base: Image.Image, source: Image.Image, x: int, y: int, size: int) -> None:
    image = crop_cover(source, size, size)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    base.paste(image, (x, y), mask)


def topic_to_query(topic: str, fallback_query: str) -> str:
    if not fallback_query.strip():
        fallback_query = "(cat OR dog OR wolf OR fox OR 宠物 OR 猫 OR 狗 OR 狼 OR 狐狸) has:media -is:retweet"

    compact = re.sub(r"\s+", "", topic.strip().lower())
    if any(keyword in compact for keyword in ("furry", "福瑞", "兽设", "兽人", "兽圈", "anthro", "kemono")):
        return (
            '("furry art" OR "furry artwork" OR "furry drawing" OR "anthro art" '
            'OR kemono OR 福瑞 OR 兽设 OR 兽人) has:media -is:retweet -nsfw -porn -18+'
        )
    if "狼" in compact or "wolf" in compact:
        return "(wolf OR wolves OR 狼 OR 狼狼) has:media -is:retweet"
    if "狐" in compact or "fox" in compact:
        return "(fox OR foxes OR 狐狸) has:media -is:retweet"
    if "猫" in compact or "cat" in compact:
        return "(cat OR cats OR 猫 OR 猫猫) has:media -is:retweet"
    if "狗" in compact or "dog" in compact:
        return "(dog OR dogs OR puppy OR 狗 OR 狗狗) has:media -is:retweet"
    if topic.strip() and not compact.startswith(("x宠物", "x热点", "x帖子", "x福瑞", "xfurry", "x兽设")):
        value = topic.strip()
        value = re.sub(r"^(x|X|推特|twitter)\s*", "", value).strip()
        if value:
            return f"({value}) has:media -is:retweet"
    return fallback_query


def normalize_bearer_token(value: str) -> str:
    token = value.strip().strip('"').strip("'")
    if token.startswith("{"):
        try:
            data = json.loads(token)
            token = str(data.get("access_token") or data.get("bearer_token") or token).strip()
        except Exception:
            pass
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token.strip().strip('"').strip("'")


def search_x_posts(
    bearer_token: str,
    query: str,
    fetch_limit: int = 30,
    timeout: int = 25,
) -> dict[str, Any]:
    token = normalize_bearer_token(bearer_token)
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
                "avatar_url": str(user.get("profile_image_url") or ""),
                "image_url": image_url,
                "score": score,
                "likes": int(metrics.get("like_count") or 0),
                "retweets": int(metrics.get("retweet_count") or 0),
                "replies": int(metrics.get("reply_count") or 0),
                "quotes": int(metrics.get("quote_count") or 0),
                "created_at": str(tweet.get("created_at") or ""),
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


def compact_count(value: Any) -> str:
    try:
        number = int(value or 0)
    except Exception:
        number = 0
    if number >= 10000:
        return f"{number / 10000:.1f}万".rstrip("0").rstrip(".")
    if number >= 1000:
        return f"{number / 1000:.1f}K".rstrip("0").rstrip(".")
    return str(number)


def post_layout(draw: ImageDraw.ImageDraw, post: dict[str, Any]) -> dict[str, Any]:
    card_width = WIDTH - PADDING * 2
    content_x = PADDING + 24 + AVATAR_SIZE + 14
    content_width = card_width - 24 - AVATAR_SIZE - 14 - 24
    text_lines = wrap_text(draw, str(post.get("text") or ""), FONT_TEXT, content_width, 6)
    image_height = 420
    text_height = max(1, len(text_lines)) * 31
    card_height = 24 + 34 + 10 + text_height + 18 + image_height + 44 + 22
    return {
        "card_width": card_width,
        "content_x": content_x,
        "content_width": content_width,
        "text_lines": text_lines,
        "image_height": image_height,
        "card_height": card_height,
    }


def draw_post_card(base: Image.Image, draw: ImageDraw.ImageDraw, y: int, post: dict[str, Any]) -> int:
    layout = post_layout(draw, post)
    x = PADDING
    width = layout["card_width"]
    height = layout["card_height"]
    content_x = layout["content_x"]
    content_width = layout["content_width"]

    draw.rounded_rectangle((x, y, x + width, y + height), radius=0, fill=CARD_BG, outline=BORDER, width=1)

    avatar = download_image(str(post.get("avatar_url") or ""))
    avatar_x = x + 24
    avatar_y = y + 24
    if avatar is not None:
        paste_circle(base, avatar, avatar_x, avatar_y, AVATAR_SIZE)
    else:
        draw.ellipse((avatar_x, avatar_y, avatar_x + AVATAR_SIZE, avatar_y + AVATAR_SIZE), fill=(32, 35, 39))

    header_y = y + 23
    name = fit_text(draw, str(post.get("name") or ""), FONT_NAME, content_width - 170)
    draw.text((content_x, header_y), name, fill=TEXT, font=FONT_NAME)
    name_width, _ = text_size(draw, name, FONT_NAME)
    handle = fit_text(draw, f' @{post.get("username", "")}', FONT_HANDLE, content_width - name_width - 8)
    draw.text((content_x + name_width + 8, header_y + 2), handle, fill=MUTED, font=FONT_HANDLE)

    text_y = y + 70
    for index, line in enumerate(layout["text_lines"]):
        draw.text((content_x, text_y + index * 31), line, fill=TEXT, font=FONT_TEXT)

    image_y = text_y + max(1, len(layout["text_lines"])) * 31 + 18
    image_box = (content_x, image_y, content_x + content_width, image_y + layout["image_height"])
    media = download_image(str(post.get("image_url") or ""))
    if media is not None:
        paste_rounded(base, media, image_box, radius=18)
    draw.rounded_rectangle(image_box, radius=18, outline=BORDER, width=1)

    metrics_y = image_box[3] + 17
    metrics = (
        f"回复 {compact_count(post.get('replies'))}    "
        f"转发 {compact_count(post.get('retweets'))}    "
        f"喜欢 {compact_count(post.get('likes'))}    "
        f"热度 {compact_count(post.get('score'))}"
    )
    draw.text((content_x, metrics_y), metrics, fill=MUTED, font=FONT_META)

    link = fit_text(draw, str(post.get("url") or ""), FONT_SMALL, content_width)
    draw.text((content_x, metrics_y + 27), link, fill=LINK, font=FONT_SMALL)
    return y + height


def render_x_posts_image(posts: list[dict[str, Any]], query: str, path: Path = OUTPUT_PATH) -> Path:
    probe = Image.new("RGB", (WIDTH, 200), PAGE_BG)
    probe_draw = ImageDraw.Draw(probe)
    card_heights = [post_layout(probe_draw, post)["card_height"] for post in posts]
    height = 96 + sum(card_heights) + max(0, len(posts) - 1) * CARD_GAP + 42

    image = Image.new("RGB", (WIDTH, height), PAGE_BG)
    draw = ImageDraw.Draw(image)

    draw.text((PADDING, 22), "X", fill=TEXT, font=FONT_TITLE)
    draw.text((PADDING + 45, 28), "热门公开帖子", fill=TEXT, font=FONT_NAME)
    subtitle = fit_text(draw, query, FONT_META, WIDTH - PADDING * 2)
    draw.text((PADDING, 62), subtitle, fill=MUTED, font=FONT_META)
    draw.line((0, 95, WIDTH, 95), fill=BORDER, width=1)

    y = 96
    for post in posts:
        y = draw_post_card(image, draw, y, post) + CARD_GAP

    footer = "Public posts via X API"
    fw, _ = text_size(draw, footer, FONT_SMALL)
    draw.text(((WIDTH - fw) // 2, height - 30), footer, fill=MUTED, font=FONT_SMALL)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=88, optimize=True)
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
        fetch_limit=int(config.get("x_search_fetch_limit") or 10),
        fallback_query=str(config.get("x_search_query") or ""),
    )
    print(caption)
    print(path)
    print(f"posts={len(posts)}")
    return 0 if posts else 1


if __name__ == "__main__":
    raise SystemExit(main())
