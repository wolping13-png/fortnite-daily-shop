from __future__ import annotations

import hashlib
import json
import math
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
SHOP_JSON_PATH = BASE_DIR / "shop.json"
OUTPUT_DIR = BASE_DIR / "shop_sections"
CACHE_DIR = BASE_DIR / ".cache" / "item_images"

WIDTH = 900
PADDING = 28
GAP = 16
COLUMNS = 3
ITEMS_PER_PAGE = 9
CARD_WIDTH = (WIDTH - PADDING * 2 - GAP * (COLUMNS - 1)) // COLUMNS
CARD_HEIGHT = 330
IMAGE_HEIGHT = 198
HEADER_HEIGHT = 76
FOOTER_HEIGHT = 36

BG = (5, 18, 39)
TEXT = (244, 249, 255)
MUTED = (184, 205, 235)
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


FONT_TITLE = load_font(32, bold=True)
FONT_NAME = load_font(22, bold=True)
FONT_META = load_font(17)
FONT_PRICE = load_font(19, bold=True)
FONT_SMALL = load_font(14)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    value = str(text or "").strip()
    if text_size(draw, value, font)[0] <= max_width:
        return value
    while value and text_size(draw, f"{value}...", font)[0] > max_width:
        value = value[:-1]
    return f"{value}..." if value else ""


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def make_gradient(
    width: int,
    height: int,
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    image = Image.new("RGB", (width, height), top)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image


def mix(color: tuple[int, int, int], other: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(color[i] * (1 - ratio) + other[i] * ratio) for i in range(3))


def rarity_palette(rarity: str) -> dict[str, tuple[int, int, int]]:
    value = str(rarity or "").lower()
    if any(token in value for token in ("神话", "mythic")):
        accent, top, bottom = (255, 224, 93), (116, 77, 14), (42, 31, 9)
    elif any(token in value for token in ("传奇", "legendary")):
        accent, top, bottom = (255, 159, 51), (112, 59, 14), (41, 26, 10)
    elif any(token in value for token in ("marvel", "漫威", "dc", "star wars", "星球大战")):
        accent, top, bottom = (255, 73, 73), (88, 25, 34), (29, 19, 30)
    elif any(token in value for token in ("史诗", "epic")):
        accent, top, bottom = (199, 91, 255), (77, 38, 117), (32, 22, 62)
    elif any(token in value for token in ("稀有", "rare")):
        accent, top, bottom = (55, 153, 255), (21, 70, 127), (11, 36, 70)
    elif any(token in value for token in ("罕见", "uncommon")):
        accent, top, bottom = (62, 207, 113), (22, 92, 57), (11, 47, 39)
    else:
        accent, top, bottom = (40, 216, 255), (18, 70, 112), (10, 34, 70)
    return {"accent": accent, "top": top, "bottom": bottom}


def clean_filename(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", value).strip("_")
    return safe[:48] or "section"


def group_items(items: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        section = str(item.get("section") or "每日商店")
        groups.setdefault(section, []).append(item)
    return list(groups.items())


def cached_image_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.img"


def download_image(url: str) -> Image.Image | None:
    if not url:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = cached_image_path(url)
    try:
        if cached.exists():
            return Image.open(cached).convert("RGBA")

        import requests

        response = requests.get(
            url,
            headers={"User-Agent": "fortnite-daily-shop-section-image/1.0"},
            timeout=25,
        )
        response.raise_for_status()
        cached.write_bytes(response.content)
        return ImageOps.exif_transpose(Image.open(BytesIO(response.content))).convert("RGBA")
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


def download_item_image(item: dict[str, Any]) -> Image.Image | None:
    for url in item_image_urls(item):
        image = download_image(url)
        if image:
            return image
    return None


def remove_white_matte(image: Image.Image) -> Image.Image:
    rgba = image.copy().convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return rgba

    fixed: list[tuple[int, int, int, int]] = []
    for red, green, blue, opacity in rgba.getdata():
        if 0 < opacity < 255:
            def unmatte(channel: int) -> int:
                value = (channel * 255 - 255 * (255 - opacity)) / opacity
                return max(0, min(255, int(round(value))))

            fixed.append((unmatte(red), unmatte(green), unmatte(blue), opacity))
        else:
            fixed.append((red, green, blue, opacity))

    rgba.putdata(fixed)
    return rgba


def paste_contained(base: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    image = remove_white_matte(image)
    image.thumbnail((right - left, bottom - top), Image.Resampling.LANCZOS)
    x = left + (right - left - image.width) // 2
    y = top + (bottom - top - image.height) // 2
    base.alpha_composite(image, (x, y))


def draw_card(
    base: Image.Image,
    draw: ImageDraw.ImageDraw,
    item: dict[str, Any],
    x: int,
    y: int,
) -> None:
    rarity = str(item.get("rarity") or "")
    palette = rarity_palette(rarity)
    card = make_gradient(CARD_WIDTH, CARD_HEIGHT, palette["top"], palette["bottom"]).convert("RGBA")
    mask = rounded_mask((CARD_WIDTH, CARD_HEIGHT), 14)
    base.paste(card, (x, y), mask)
    draw.rounded_rectangle((x, y, x + CARD_WIDTH, y + CARD_HEIGHT), radius=14, outline=palette["accent"], width=3)
    draw.rounded_rectangle((x + 12, y + 11, x + CARD_WIDTH - 12, y + 18), radius=4, fill=palette["accent"])

    image_area = (x + 12, y + 24, x + CARD_WIDTH - 12, y + 24 + IMAGE_HEIGHT)
    draw.rounded_rectangle(image_area, radius=12, fill=mix(palette["top"], (255, 255, 255), 0.12))

    image = download_item_image(item)
    if image:
        paste_contained(base, image, image_area)
    else:
        label = "NO IMAGE"
        w, h = text_size(draw, label, FONT_META)
        draw.text(
            (image_area[0] + (image_area[2] - image_area[0] - w) // 2, image_area[1] + 86),
            label,
            fill=MUTED,
            font=FONT_META,
        )

    info = (x + 10, y + 236, x + CARD_WIDTH - 10, y + CARD_HEIGHT - 10)
    draw.rounded_rectangle(info, radius=12, fill=(3, 12, 31, 136))

    name = fit_text(draw, str(item.get("name") or "未知物品"), FONT_NAME, CARD_WIDTH - 32)
    draw.text((x + 16, y + 248), name, fill=TEXT, font=FONT_NAME)

    rarity_text = fit_text(draw, rarity or "未知稀有度", FONT_META, CARD_WIDTH - 32)
    draw.text((x + 16, y + 281), rarity_text, fill=MUTED, font=FONT_META)

    price = f"{int(item.get('price') or 0):,} V-Bucks"
    draw.text((x + 16, y + 306), price, fill=YELLOW, font=FONT_PRICE)


def draw_page(
    section: str,
    page_items: list[dict[str, Any]],
    page_index: int,
    total_pages: int,
    global_index: int,
) -> tuple[Path, str]:
    rows = max(1, math.ceil(len(page_items) / COLUMNS))
    height = PADDING * 2 + HEADER_HEIGHT + rows * CARD_HEIGHT + max(0, rows - 1) * GAP + FOOTER_HEIGHT
    image = make_gradient(WIDTH, height, BG, (2, 8, 23)).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")

    for offset in range(-WIDTH, height, 80):
        draw.line((0, offset, WIDTH, offset + WIDTH), fill=(255, 255, 255, 13), width=2)

    header = (PADDING, PADDING, WIDTH - PADDING, PADDING + HEADER_HEIGHT - 18)
    draw.rounded_rectangle(header, radius=16, fill=(3, 12, 31, 190), outline=YELLOW, width=2)
    title = fit_text(draw, f"{section}", FONT_TITLE, WIDTH - PADDING * 2 - 220)
    draw.text((PADDING + 20, PADDING + 15), title, fill=TEXT, font=FONT_TITLE)
    page_text = f"{page_index}/{total_pages}"
    pw, ph = text_size(draw, page_text, FONT_META)
    draw.rounded_rectangle((WIDTH - PADDING - pw - 42, PADDING + 21, WIDTH - PADDING - 16, PADDING + 21 + ph + 16), radius=12, fill=(255, 212, 56, 64))
    draw.text((WIDTH - PADDING - pw - 29, PADDING + 29), page_text, fill=TEXT, font=FONT_META)
    draw.text((PADDING + 20, PADDING + 54), "Fortnite 每日商店", fill=MUTED, font=FONT_META)

    start_y = PADDING + HEADER_HEIGHT
    for index, item in enumerate(page_items):
        col = index % COLUMNS
        row = index // COLUMNS
        x = PADDING + col * (CARD_WIDTH + GAP)
        y = start_y + row * (CARD_HEIGHT + GAP)
        draw_card(image, draw, item, x, y)

    footer = "发送“商店全部”可查看全部分页"
    fw, _ = text_size(draw, footer, FONT_SMALL)
    draw.text(((WIDTH - fw) // 2, height - 34), footer, fill=(126, 157, 196), font=FONT_SMALL)

    safe_section = clean_filename(section)
    path = OUTPUT_DIR / f"{global_index:02d}_{safe_section}_{page_index}.jpg"
    image.convert("RGB").save(path, quality=82, optimize=True)
    caption = f"{section} ({page_index}/{total_pages})"
    return path, caption


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in OUTPUT_DIR.glob("*.jpg"):
        old_file.unlink()

    data = json.loads(SHOP_JSON_PATH.read_text(encoding="utf-8"))
    items = [item for item in data.get("items", []) if isinstance(item, dict)]
    pages: list[dict[str, str]] = []

    global_index = 1
    for section, section_items in group_items(items):
        chunks = [section_items[index : index + ITEMS_PER_PAGE] for index in range(0, len(section_items), ITEMS_PER_PAGE)]
        total_pages = len(chunks)
        for page_index, chunk in enumerate(chunks, 1):
            path, caption = draw_page(section, chunk, page_index, total_pages, global_index)
            pages.append({"path": str(path.relative_to(BASE_DIR)), "caption": caption})
            print(path, path.stat().st_size)
            global_index += 1

    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps({"pages": pages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(pages)} shop section images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
