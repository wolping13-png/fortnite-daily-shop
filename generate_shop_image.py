from __future__ import annotations

import json
import math
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

WIDTH = 1080
PADDING = 36
GAP = 18
COLUMNS = 3
CARD_WIDTH = (WIDTH - PADDING * 2 - GAP * (COLUMNS - 1)) // COLUMNS
CARD_HEIGHT = 440
IMAGE_HEIGHT = 248
HEADER_HEIGHT = 170
SECTION_TITLE_HEIGHT = 76
SECTION_GAP = 42
FOOTER_HEIGHT = 70

BG_TOP = (6, 19, 41)
BG_BOTTOM = (2, 8, 23)
CARD_BG = (14, 45, 92)
CARD_BG_2 = (13, 34, 70)
LINE = (80, 145, 220)
TEXT = (244, 249, 255)
MUTED = (167, 195, 230)
YELLOW = (255, 212, 56)
CYAN = (40, 216, 255)

REQUEST_TIMEOUT = 25


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


FONT_TITLE = load_font(56, bold=True)
FONT_SECTION = load_font(34, bold=True)
FONT_NAME = load_font(25, bold=True)
FONT_META = load_font(19, bold=True)
FONT_SMALL = load_font(17, bold=False)
FONT_PRICE = load_font(26, bold=True)


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

    try:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": "fortnite-daily-shop-image/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        return ImageOps.exif_transpose(image).convert("RGBA")
    except Exception:
        return None


def group_items(items: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        section = clean_section_name(item.get("section"))
        groups.setdefault(section, []).append(item)
    return list(groups.items())


def clean_section_name(value: Any) -> str:
    section = str(value or "").strip()
    if not section or section.lower() in {"daily shop", "shop", "unknown"}:
        return "每日商店"
    return section


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
    shadow = (x + 7, y + 8, x + CARD_WIDTH + 7, y + CARD_HEIGHT + 8)
    draw.rounded_rectangle(shadow, radius=18, fill=(0, 0, 0, 80))

    card = (x, y, x + CARD_WIDTH, y + CARD_HEIGHT)
    paste_rounded_gradient(base, x, y, CARD_WIDTH, CARD_HEIGHT, palette["top"], palette["bottom"], 18)
    draw.rounded_rectangle(card, radius=18, outline=palette["accent"], width=3)
    draw.rounded_rectangle((x + 3, y + 3, x + CARD_WIDTH - 3, y + CARD_HEIGHT - 3), radius=15, outline=(255, 255, 255, 36), width=1)
    draw.rounded_rectangle((x + 16, y + 14, x + CARD_WIDTH - 16, y + 22), radius=4, fill=palette["accent"])

    image_area = (x + 14, y + 34, x + CARD_WIDTH - 14, y + 34 + IMAGE_HEIGHT)
    paste_rounded_gradient(
        base,
        image_area[0],
        image_area[1],
        image_area[2] - image_area[0],
        image_area[3] - image_area[1],
        mix_color(palette["top"], (255, 255, 255), 0.12),
        mix_color(palette["bottom"], (0, 0, 0), 0.05),
        14,
    )
    draw.rounded_rectangle(image_area, radius=14, outline=(255, 255, 255, 34), width=1)

    image = download_image(str(item.get("image") or ""))
    if image:
        paste_contained(base, image, image_area)
    else:
        draw.text((image_area[0] + 26, image_area[1] + 92), "NO IMAGE", fill=MUTED, font=FONT_META)

    info_panel = (x + 12, y + 300, x + CARD_WIDTH - 12, y + CARD_HEIGHT - 12)
    draw.rounded_rectangle(info_panel, radius=14, fill=(3, 12, 31, 122))

    name_y = y + 315
    name_lines = wrap_lines(draw, str(item.get("name") or "Unknown Item"), FONT_NAME, CARD_WIDTH - 30, 2)
    for line in name_lines:
        draw.text((x + 15, name_y), line, fill=TEXT, font=FONT_NAME)
        name_y += 30

    draw_badge(draw, (x + 15, y + CARD_HEIGHT - 52), rarity, FONT_SMALL, palette["badge"], CARD_WIDTH - 128)

    price_text = f"{int(item.get('price') or 0):,}"
    price_width, price_height = text_size(draw, price_text, FONT_PRICE)
    price_box_width = price_width + 54
    price_box = (x + CARD_WIDTH - 16 - price_box_width, y + CARD_HEIGHT - 57, x + CARD_WIDTH - 15, y + CARD_HEIGHT - 18)
    draw.rounded_rectangle(price_box, radius=12, fill=(0, 0, 0, 116), outline=(255, 212, 56, 118), width=1)
    price_x = price_box[2] - 12 - price_width
    icon_size = 28
    if vbuck_icon:
        price_x -= icon_size + 7
        icon = vbuck_icon.copy()
        icon.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)
        base.alpha_composite(icon, (price_x, y + CARD_HEIGHT - 51))
        text_x = price_x + icon_size + 7
    else:
        text_x = price_x

    draw.text((text_x, y + CARD_HEIGHT - 54), price_text, fill=YELLOW, font=FONT_PRICE)


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
        height += SECTION_TITLE_HEIGHT + rows * CARD_HEIGHT + max(0, rows - 1) * GAP + SECTION_GAP

    return height + FOOTER_HEIGHT


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
    box = (PADDING, y, WIDTH - PADDING, y + SECTION_TITLE_HEIGHT - 14)
    draw.rounded_rectangle(box, radius=16, fill=(3, 12, 31, 184), outline=(255, 255, 255, 30), width=1)
    draw.rounded_rectangle((box[0] + 12, box[1] + 12, box[0] + 22, box[3] - 12), radius=5, fill=accent)

    title = fit_text(draw, str(section_name), FONT_SECTION, WIDTH - PADDING * 2 - 210)
    draw.text((box[0] + 38, box[1] + 14), title, fill=TEXT, font=FONT_SECTION)

    count_text = f"{item_count} 件商品"
    count_width, count_height = text_size(draw, count_text, FONT_META)
    pill = (
        box[2] - count_width - 42,
        box[1] + 16,
        box[2] - 16,
        box[1] + 16 + count_height + 16,
    )
    draw.rounded_rectangle(pill, radius=12, fill=mix_color(accent, (0, 0, 0), 0.62))
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

    image.save(target, quality=75, optimize=True)


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
    draw.text((PADDING, PADDING + 82), f"更新时间：{parse_date(data.get('updatedAt') or data.get('date'))}", fill=MUTED, font=FONT_META)
    draw.text((PADDING, PADDING + 112), "数据来源：fortnite-api.com", fill=(123, 164, 213), font=FONT_SMALL)

    vbuck_icon = download_image(str(data.get("vbuckIcon") or ""))

    y = PADDING + HEADER_HEIGHT
    for section_index, (section_name, section_items) in enumerate(groups):
        draw_section_header(draw, y, str(section_name), len(section_items), section_index)
        y += SECTION_TITLE_HEIGHT

        for index, item in enumerate(section_items):
            col = index % COLUMNS
            row = index // COLUMNS
            x = PADDING + col * (CARD_WIDTH + GAP)
            card_y = y + row * (CARD_HEIGHT + GAP)
            draw_card(image, draw, item, x, card_y, vbuck_icon)

        rows = max(1, math.ceil(len(section_items) / COLUMNS))
        y += rows * CARD_HEIGHT + max(0, rows - 1) * GAP + SECTION_GAP

    footer = "图片地址：/shop.png"
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
