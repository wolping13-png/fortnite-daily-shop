from __future__ import annotations

import hashlib
import json
import math
import os
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
SHOP_JSON_PATH = BASE_DIR / "shop.json"
OUTPUT_PATH = BASE_DIR / "shop.png"
QQ_OUTPUT_PATH = BASE_DIR / "shop_qq.jpg"
CACHE_DIR = BASE_DIR / ".cache" / "item_images"

WIDTH = 1080
PADDING = 32
GAP = 12
COLUMNS = 4
SECTION_INSET = 16
GRID_LEFT = PADDING + SECTION_INSET
GRID_WIDTH = WIDTH - GRID_LEFT * 2
CARD_WIDTH = (GRID_WIDTH - GAP * (COLUMNS - 1)) // COLUMNS
CARD_HEIGHT = 268
IMAGE_HEIGHT = 152
HEADER_HEIGHT = 132
SECTION_TITLE_HEIGHT = 66
SECTION_GAP = 44
FOOTER_HEIGHT = 56

BG_TOP = (6, 19, 41)
BG_BOTTOM = (2, 8, 23)
CARD_BG = (14, 45, 92)
CARD_BG_2 = (13, 34, 70)
LINE = (80, 145, 220)
TEXT = (244, 249, 255)
MUTED = (167, 195, 230)
YELLOW = (255, 212, 56)
CYAN = (40, 216, 255)

REQUEST_TIMEOUT = 12
TARGET_QQ_BYTES = 4_500_000


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
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)

    return ImageFont.load_default()


FONT_TITLE = load_font(46, bold=True)
FONT_SECTION = load_font(25, bold=True)
FONT_NAME = load_font(18, bold=True)
FONT_META = load_font(14, bold=True)
FONT_SMALL = load_font(13, bold=False)
FONT_PRICE = load_font(18, bold=True)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    value = str(text or "").strip()
    if text_size(draw, value, font)[0] <= max_width:
        return value

    while value and text_size(draw, f"{value}...", font)[0] > max_width:
        value = value[:-1]
    return f"{value}..." if value else ""


def wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = str(text or "").replace("\n", " ").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        attempt = f"{current} {word}".strip()
        if text_size(draw, attempt, font)[0] <= max_width:
            current = attempt
            continue

        if current:
            lines.append(current)
        current = word

        if len(lines) == max_lines:
            break

    if len(lines) < max_lines and current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    if lines and text_size(draw, lines[-1], font)[0] > max_width:
        lines[-1] = fit_text(draw, lines[-1], font, max_width)

    remaining = " ".join(words)
    displayed = " ".join(lines)
    if len(lines) == max_lines and len(displayed) < len(remaining):
        lines[-1] = fit_text(draw, lines[-1], font, max_width - 10)

    return lines


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def make_gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (width, height), top)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def download_image(url: str) -> Image.Image | None:
    if not url:
        return None
    if os.environ.get("FORTNITE_SKIP_IMAGE_DOWNLOADS") == "1":
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.img"
    try:
        if cached.exists():
            return ImageOps.exif_transpose(Image.open(cached)).convert("RGBA")

        import requests

        response = requests.get(
            url,
            headers={
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Referer": "https://fortnite-api.com/",
                "User-Agent": "Mozilla/5.0 fortnite-daily-shop-image/1.0",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        cached.write_bytes(response.content)
        image = Image.open(BytesIO(response.content))
        return ImageOps.exif_transpose(image).convert("RGBA")
    except Exception:
        return None


def item_image_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    tile_image = item.get("tileImage")
    if isinstance(tile_image, str) and tile_image.startswith("http"):
        urls.append(tile_image)

    image = item.get("image")
    if isinstance(image, str) and image.startswith("http"):
        if image not in urls:
            urls.append(image)

    images = item.get("images")
    if isinstance(images, list):
        for value in images:
            if isinstance(value, str) and value.startswith("http") and value not in urls:
                urls.append(value)

    return urls


def download_tile_image(item: dict[str, Any]) -> Image.Image | None:
    tile_image = item.get("tileImage")
    if isinstance(tile_image, str) and tile_image.startswith("http"):
        return download_image(tile_image)
    return None


def download_item_image(item: dict[str, Any]) -> Image.Image | None:
    for url in item_image_urls(item):
        image = download_image(url)
        if image:
            return image
    return None


def clean_section_name(value: Any) -> str:
    section = str(value or "").strip()
    if not section or section.lower() == "unknown":
        return "Daily Shop"
    return section


GENERIC_SECTION_NAMES = {
    "daily shop",
    "每日商店",
    "shop",
    "featured",
    "unknown",
}


COLLECTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Overwatch",
        (
            "overwatch",
            "守望先锋",
            "mercy",
            "tracer",
            "d.va",
            "dva",
            "genji",
            "hanzo",
            "mei",
            "reaper",
            "widowmaker",
            "lucio",
            "lúcio",
            "zarya",
            "天使",
            "猎空",
            "d.va",
            "源氏",
            "半藏",
            "小美",
            "死神",
            "黑百合",
            "卢西奥",
            "查莉娅",
            "龙一文字",
            "竜一文字",
            "脉冲炸弹",
            "脉冲双刀",
            "小兔机甲",
            "女武神之翼",
            "酷炫闪现",
        ),
    ),
    ("Cyberpunk 2077", ("cyberpunk", "赛博朋克", "强尼", "银手", "夜之城", "johnny", "silverhand")),
    ("Star Wars", ("star wars", "星球大战", "sith", "jedi", "rebel", "empire", "imperial", "tatooine", "kylo", "lightsaber", "stormtrooper", "西斯", "绝地", "义军", "帝国", "塔图因", "凯洛", "光剑")),
    ("Regular Show", ("regular show", "mordecai", "rigby")),
    ("Porsche", ("porsche", "保时捷", "cayenne", "卡宴")),
    ("Jam Tracks", ("jam track", "jam tracks", "music", "song", "歌曲", "曲目", "音乐", "伴奏")),
)


ACTION_TYPE_TOKENS = (
    "emote",
    "emoji",
    "spray",
    "toy",
    "表情",
    "动作",
    "喷漆",
    "玩具",
    "姿势",
    "舞步",
    "舞蹈",
    "日日夜夜",
    "跑起来",
    "跳跳",
    "石头剪子布",
    "scouse",
    "stepper",
    "rhyme dust",
    "静心茶",
    "哦哦哦",
)


def lower_blob(item: dict[str, Any]) -> str:
    parts = [
        item.get("name"),
        item.get("rarity"),
        item.get("series"),
        item.get("set"),
        item.get("type"),
        item.get("section"),
        item.get("layoutName"),
        item.get("layoutId"),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def is_generic_section(value: Any) -> bool:
    return clean_section_name(value).strip().lower() in GENERIC_SECTION_NAMES


def derived_group_name(item: dict[str, Any]) -> str:
    section = clean_section_name(item.get("section"))
    layout_name = clean_section_name(item.get("layoutName"))
    blob = lower_blob(item)

    if not is_generic_section(section):
        return section
    if not is_generic_section(layout_name):
        return layout_name

    for label, tokens in COLLECTION_PATTERNS:
        if any(token in blob for token in tokens):
            return label

    item_type = str(item.get("type") or "").strip()
    if any(token in blob for token in ACTION_TYPE_TOKENS):
        return "动作 / 表情"

    set_name = str(item.get("set") or "").strip()
    if set_name:
        return set_name

    series = str(item.get("series") or "").strip()
    if series and series.lower() not in {"unknown", "未知"}:
        return series

    return section


def item_entry_index(item: dict[str, Any]) -> int:
    try:
        return int(item.get("entryIndex") or 0)
    except Exception:
        return 0


def item_sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
    try:
        section_rank = int(item.get("sectionRank") or item_entry_index(item))
    except Exception:
        section_rank = item_entry_index(item)
    try:
        sort_priority = int(item.get("sortPriority") or 0)
    except Exception:
        sort_priority = 0
    return (section_rank, sort_priority, item_entry_index(item))


def group_items(items: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    first_seen: dict[str, int] = {}
    for index, item in enumerate(items):
        section = derived_group_name(item)
        groups.setdefault(section, []).append(item)
        first_seen.setdefault(section, index)

    result: list[tuple[str, list[dict[str, Any]]]] = []
    for section, section_items in groups.items():
        section_items.sort(key=item_sort_key)
        result.append((section, section_items))

    result.sort(key=lambda group: (min(item_sort_key(item)[0] for item in group[1]), first_seen[group[0]]))
    return result


def contains_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)


def mix_color(color: tuple[int, int, int], other: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(color[index] * (1 - ratio) + other[index] * ratio) for index in range(3))


def rarity_palette(rarity: str) -> dict[str, tuple[int, int, int]]:
    value = str(rarity or "").lower()
    if contains_any(value, ("神话", "mythic")):
        accent = (255, 224, 93)
        top = (116, 77, 14)
        bottom = (42, 31, 9)
    elif contains_any(value, ("传奇", "legendary", "lava", "熔岩")):
        accent = (255, 159, 51)
        top = (112, 59, 14)
        bottom = (41, 26, 10)
    elif contains_any(value, ("marvel", "漫威", "dc", "黑暗", "dark")):
        accent = (255, 68, 128)
        top = (90, 26, 70)
        bottom = (31, 20, 48)
    elif contains_any(value, ("star wars", "星球大战", "gaming", "游戏")):
        accent = (255, 73, 73)
        top = (88, 25, 34)
        bottom = (29, 19, 30)
    elif contains_any(value, ("偶像", "icon")):
        accent = (40, 216, 255)
        top = (21, 82, 104)
        bottom = (10, 35, 55)
    elif contains_any(value, ("史诗", "epic")):
        accent = (199, 91, 255)
        top = (77, 38, 117)
        bottom = (32, 22, 62)
    elif contains_any(value, ("稀有", "rare")):
        accent = (55, 153, 255)
        top = (21, 70, 127)
        bottom = (11, 36, 70)
    elif contains_any(value, ("罕见", "uncommon")):
        accent = (62, 207, 113)
        top = (22, 92, 57)
        bottom = (11, 47, 39)
    elif contains_any(value, ("普通", "common")):
        accent = (176, 190, 209)
        top = (58, 72, 90)
        bottom = (25, 32, 45)
    else:
        accent = CYAN
        top = (18, 70, 112)
        bottom = (10, 34, 70)

    return {
        "accent": accent,
        "top": top,
        "bottom": bottom,
        "image": mix_color(top, (255, 255, 255), 0.08),
        "badge": mix_color(accent, (0, 0, 0), 0.38),
    }


def rarity_color(rarity: str) -> tuple[int, int, int]:
    return rarity_palette(rarity)["accent"]


def draw_badge(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
) -> None:
    x, y = xy
    label = fit_text(draw, text, font, max_width - 24)
    width, height = text_size(draw, label, font)
    draw.rounded_rectangle((x, y, x + width + 22, y + height + 14), radius=10, fill=fill)
    draw.text((x + 11, y + 7), label, fill=TEXT, font=font)


def paste_contained(
    base: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top
    image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    x = left + (max_width - image.width) // 2
    y = top + (max_height - image.height) // 2
    base.alpha_composite(image, (x, y))


def paste_cover(
    base: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    source = image.copy().convert("RGBA")
    scale = max(width / source.width, height / source.height)
    resized = source.resize(
        (max(1, int(source.width * scale)), max(1, int(source.height * scale))),
        Image.Resampling.LANCZOS,
    )
    x = max(0, (resized.width - width) // 2)
    y = max(0, (resized.height - height) // 2)
    cropped = resized.crop((x, y, x + width, y + height))
    mask = rounded_mask((width, height), radius)
    base.paste(cropped, (left, top), mask)


def paste_rounded_gradient(
    base: Image.Image,
    x: int,
    y: int,
    width: int,
    height: int,
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
    radius: int,
) -> None:
    panel = make_gradient(width, height, top, bottom).convert("RGBA")
    mask = rounded_mask((width, height), radius)
    base.paste(panel, (x, y), mask)


def draw_card(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    item: dict[str, Any],
    x: int,
    y: int,
    vbuck_icon: Image.Image | None,
) -> None:
    rarity = str(item.get("rarity") or "Unknown")
    palette = rarity_palette(rarity)
    radius = 12
    shadow = (x + 5, y + 7, x + CARD_WIDTH + 5, y + CARD_HEIGHT + 7)
    draw.rounded_rectangle(shadow, radius=radius, fill=(0, 0, 0, 90))

    card = (x, y, x + CARD_WIDTH, y + CARD_HEIGHT)
    paste_rounded_gradient(base, x, y, CARD_WIDTH, CARD_HEIGHT, palette["top"], palette["bottom"], radius)

    tile_image = download_tile_image(item)
    if tile_image:
        paste_cover(base, tile_image, card, radius)
    else:
        image_area = (x + 13, y + 16, x + CARD_WIDTH - 13, y + 16 + IMAGE_HEIGHT)
        paste_rounded_gradient(
            base,
            image_area[0],
            image_area[1],
            image_area[2] - image_area[0],
            image_area[3] - image_area[1],
            mix_color(palette["top"], (255, 255, 255), 0.12),
            mix_color(palette["bottom"], (0, 0, 0), 0.05),
            10,
        )
        image = download_item_image(item)
        if image:
            paste_contained(base, image, image_area)
        else:
            label = "NO IMAGE"
            label_width, label_height = text_size(draw, label, FONT_META)
            draw.text(
                (
                    image_area[0] + (image_area[2] - image_area[0] - label_width) // 2,
                    image_area[1] + (image_area[3] - image_area[1] - label_height) // 2,
                ),
                label,
                fill=MUTED,
                font=FONT_META,
            )

    draw.rounded_rectangle(card, radius=radius, outline=palette["accent"], width=3)
    draw.rounded_rectangle((x + 3, y + 3, x + CARD_WIDTH - 3, y + CARD_HEIGHT - 3), radius=radius - 2, outline=(255, 255, 255, 42), width=1)
    draw.rounded_rectangle((x + 12, y + 11, x + CARD_WIDTH - 12, y + 18), radius=4, fill=palette["accent"])

    info_panel = (x + 12, y + CARD_HEIGHT - 92, x + CARD_WIDTH - 12, y + CARD_HEIGHT - 12)
    draw.rounded_rectangle(info_panel, radius=11, fill=(2, 8, 23, 184))

    name = fit_text(draw, str(item.get("name") or "Unknown Item"), FONT_NAME, CARD_WIDTH - 30)
    draw.text((x + 18, y + CARD_HEIGHT - 84), name, fill=TEXT, font=FONT_NAME)

    rarity_text = fit_text(draw, rarity, FONT_META, CARD_WIDTH - 132)
    draw.text((x + 18, y + CARD_HEIGHT - 52), rarity_text, fill=MUTED, font=FONT_META)

    price_text = f"{int(item.get('price') or 0):,}"
    price_width, price_height = text_size(draw, price_text, FONT_PRICE)
    price_box_width = price_width + 52
    price_box = (
        x + CARD_WIDTH - 18 - price_box_width,
        y + CARD_HEIGHT - 57,
        x + CARD_WIDTH - 18,
        y + CARD_HEIGHT - 22,
    )
    draw.rounded_rectangle(price_box, radius=9, fill=(0, 0, 0, 132), outline=(255, 212, 56, 128), width=1)
    price_x = price_box[2] - 10 - price_width
    icon_size = 24
    if vbuck_icon:
        price_x -= icon_size + 7
        icon = vbuck_icon.copy()
        icon.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)
        base.alpha_composite(icon, (price_x, y + CARD_HEIGHT - 52))
        text_x = price_x + icon_size + 7
    else:
        text_x = price_x

    draw.text((text_x, y + CARD_HEIGHT - 57), price_text, fill=YELLOW, font=FONT_PRICE)


def parse_date(value: Any) -> str:
    if not value:
        return "等待首次更新"

    try:
        text = str(value).replace("Z", "+00:00")
        date = datetime.fromisoformat(text)
        return date.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value)


def calculate_height(groups: list[tuple[str, list[dict[str, Any]]]]) -> int:
    if not groups:
        return 720

    height = PADDING + HEADER_HEIGHT
    for _, items in groups:
        rows = max(1, math.ceil(len(items) / COLUMNS))
        section_height = (
            SECTION_INSET * 2
            + SECTION_TITLE_HEIGHT
            + rows * CARD_HEIGHT
            + max(0, rows - 1) * GAP
        )
        height += section_height + SECTION_GAP

    return height + FOOTER_HEIGHT


def draw_section_panel(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    height: int,
    index: int,
) -> None:
    accents = [
        (255, 212, 56),
        (40, 216, 255),
        (255, 79, 179),
        (82, 227, 158),
        (255, 147, 64),
    ]
    accent = accents[index % len(accents)]
    x = PADDING
    width = WIDTH - PADDING * 2

    shadow = (x + 5, y + 7, x + width + 5, y + height + 7)
    draw.rounded_rectangle(shadow, radius=22, fill=(0, 0, 0, 90))
    paste_rounded_gradient(base, x, y, width, height, (8, 30, 65), (3, 13, 32), 22)
    draw.rounded_rectangle((x, y, x + width, y + height), radius=22, outline=mix_color(accent, (255, 255, 255), 0.18), width=2)
    draw.rounded_rectangle((x + 2, y + 2, x + width - 2, y + height - 2), radius=20, outline=(255, 255, 255, 22), width=1)


def draw_section_header(
    draw: ImageDraw.ImageDraw,
    y: int,
    section_name: str,
    item_count: int,
    index: int,
) -> None:
    accents = [
        (255, 212, 56),
        (40, 216, 255),
        (255, 79, 179),
        (82, 227, 158),
        (255, 147, 64),
    ]
    accent = accents[index % len(accents)]
    box = (GRID_LEFT, y, WIDTH - GRID_LEFT, y + SECTION_TITLE_HEIGHT - 12)
    draw.rounded_rectangle(box, radius=16, fill=(3, 12, 31, 210), outline=(255, 255, 255, 38), width=1)
    draw.rounded_rectangle((box[0], box[1], box[0] + 9, box[3]), radius=4, fill=accent)

    title = fit_text(draw, str(section_name), FONT_SECTION, GRID_WIDTH - 216)
    draw.text((box[0] + 26, box[1] + 10), title, fill=TEXT, font=FONT_SECTION)
    draw.text((box[0] + 27, box[1] + 39), "SHOP SECTION", fill=(123, 164, 213), font=FONT_SMALL)

    count_text = f"{item_count} 件"
    count_width, count_height = text_size(draw, count_text, FONT_META)
    pill = (
        box[2] - count_width - 42,
        box[1] + 14,
        box[2] - 16,
        box[1] + 14 + count_height + 16,
    )
    draw.rounded_rectangle(pill, radius=10, fill=mix_color(accent, (0, 0, 0), 0.62))
    draw.text((pill[0] + 13, pill[1] + 8), count_text, fill=TEXT, font=FONT_META)


def draw_placeholder(path: Path) -> None:
    image = make_gradient(WIDTH, 720, BG_TOP, BG_BOTTOM).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((PADDING, 210), "FORTNITE 每日商店", fill=TEXT, font=FONT_TITLE)
    draw.text((PADDING, 286), "运行 update_shop.py 生成最新商店图片", fill=MUTED, font=FONT_SECTION)
    image.convert("RGB").save(path, optimize=True)


def save_qq_image(source: Path = OUTPUT_PATH, target: Path = QQ_OUTPUT_PATH) -> None:
    if not source.exists():
        return

    image = Image.open(source).convert("RGB")
    max_width = 900
    if image.width > max_width:
        height = int(image.height * max_width / image.width)
        image = image.resize((max_width, height), Image.Resampling.LANCZOS)

    for quality in (76, 70, 64, 58):
        image.save(target, quality=quality, optimize=True)
        if target.stat().st_size <= TARGET_QQ_BYTES:
            return

    if target.stat().st_size > TARGET_QQ_BYTES and image.width > 780:
        height = int(image.height * 780 / image.width)
        smaller = image.resize((780, height), Image.Resampling.LANCZOS)
        smaller.save(target, quality=60, optimize=True)


def render_shop_image() -> None:
    if not SHOP_JSON_PATH.exists():
        draw_placeholder(OUTPUT_PATH)
        save_qq_image()
        return

    data = json.loads(SHOP_JSON_PATH.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else []
    if not isinstance(items, list) or not items:
        draw_placeholder(OUTPUT_PATH)
        save_qq_image()
        return

    groups = group_items([item for item in items if isinstance(item, dict)])
    height = calculate_height(groups)
    image = make_gradient(WIDTH, height, BG_TOP, BG_BOTTOM).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")

    for offset in range(-WIDTH, height, 90):
        draw.line((0, offset, WIDTH, offset + WIDTH), fill=(255, 255, 255, 10), width=2)

    title = "FORTNITE 每日商店"
    draw.text((PADDING, PADDING + 12), title, fill=TEXT, font=FONT_TITLE)
    draw.text((PADDING, PADDING + 66), f"更新时间：{parse_date(data.get('updatedAt') or data.get('date'))}", fill=MUTED, font=FONT_META)
    draw.text((PADDING, PADDING + 91), "完整商店 · 按官方货架 / 系列 / 类型分组排列", fill=(123, 164, 213), font=FONT_SMALL)

    vbuck_icon = download_image(str(data.get("vbuckIcon") or ""))

    y = PADDING + HEADER_HEIGHT
    for section_index, (section_name, section_items) in enumerate(groups):
        rows = max(1, math.ceil(len(section_items) / COLUMNS))
        section_height = (
            SECTION_INSET * 2
            + SECTION_TITLE_HEIGHT
            + rows * CARD_HEIGHT
            + max(0, rows - 1) * GAP
        )
        draw_section_panel(image, draw, y, section_height, section_index)

        header_y = y + SECTION_INSET
        draw_section_header(draw, header_y, str(section_name), len(section_items), section_index)
        grid_y = header_y + SECTION_TITLE_HEIGHT
        for index, item in enumerate(section_items):
            col = index % COLUMNS
            row = index // COLUMNS
            x = GRID_LEFT + col * (CARD_WIDTH + GAP)
            card_y = grid_y + row * (CARD_HEIGHT + GAP)
            draw_card(image, draw, item, x, card_y, vbuck_icon)

        y += section_height + SECTION_GAP

    footer = "完整商城总图 · 优先按官方货架分组，缺失时按系列和类型归类"
    footer_width, _ = text_size(draw, footer, FONT_SMALL)
    draw.text(((WIDTH - footer_width) // 2, height - 44), footer, fill=(116, 150, 190), font=FONT_SMALL)

    image.convert("RGB").save(OUTPUT_PATH, optimize=True)
    save_qq_image()


def main() -> int:
    render_shop_image()
    print(f"Saved shop image to {OUTPUT_PATH.name}")
    if QQ_OUTPUT_PATH.exists():
        print(f"Saved QQ image to {QQ_OUTPUT_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
