from __future__ import annotations

import hashlib
import random
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "random_food"
OUTPUT_PATH = BASE_DIR / "random_food.jpg"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"

REQUEST_TIMEOUT = 18
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

FOODS = [
    {"name": "火锅", "query": "hot pot food"},
    {"name": "饺子", "query": "jiaozi dumplings"},
    {"name": "牛肉面", "query": "beef noodle soup"},
    {"name": "拉面", "query": "ramen noodles"},
    {"name": "寿司", "query": "sushi"},
    {"name": "披萨", "query": "pizza"},
    {"name": "炸鸡", "query": "fried chicken"},
    {"name": "汉堡", "query": "hamburger"},
    {"name": "烤肉", "query": "barbecue meat"},
    {"name": "炒饭", "query": "fried rice"},
    {"name": "咖喱饭", "query": "curry rice"},
    {"name": "麻辣烫", "query": "malatang"},
    {"name": "烤鱼", "query": "grilled fish"},
    {"name": "螺蛳粉", "query": "luosifen"},
    {"name": "沙县小吃", "query": "Chinese wonton noodles"},
    {"name": "黄焖鸡米饭", "query": "braised chicken rice"},
    {"name": "煲仔饭", "query": "claypot rice"},
    {"name": "盖浇饭", "query": "rice bowl food"},
    {"name": "小笼包", "query": "xiaolongbao"},
    {"name": "烤冷面", "query": "Chinese street food noodles"},
    {"name": "三明治", "query": "sandwich"},
    {"name": "意大利面", "query": "spaghetti pasta"},
    {"name": "日式便当", "query": "bento"},
    {"name": "墨西哥卷饼", "query": "tacos"},
]

DRINKS = [
    {"name": "珍珠奶茶", "query": "bubble tea"},
    {"name": "冰美式", "query": "iced americano coffee"},
    {"name": "拿铁", "query": "latte coffee"},
    {"name": "柠檬茶", "query": "lemon iced tea"},
    {"name": "椰子水", "query": "coconut water drink"},
    {"name": "橙汁", "query": "orange juice"},
    {"name": "酸梅汤", "query": "suanmeitang"},
    {"name": "可乐", "query": "cola drink glass"},
    {"name": "热巧克力", "query": "hot chocolate drink"},
    {"name": "抹茶拿铁", "query": "matcha latte"},
    {"name": "乌龙茶", "query": "oolong tea"},
    {"name": "茉莉花茶", "query": "jasmine tea"},
    {"name": "豆浆", "query": "soy milk"},
    {"name": "气泡水", "query": "sparkling water"},
    {"name": "芒果冰沙", "query": "mango smoothie"},
    {"name": "草莓奶昔", "query": "strawberry milkshake"},
    {"name": "西瓜汁", "query": "watermelon juice"},
    {"name": "姜汁汽水", "query": "ginger ale"},
]


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
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_BIG = load_font(72, True)
FONT_TITLE = load_font(38, True)
FONT_TEXT = load_font(25, False)
FONT_SMALL = load_font(18, False)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def commons_image_url(session: requests.Session, query: str) -> str:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": query,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": 1100,
    }
    response = session.get(COMMONS_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return ""

    for page in pages.values():
        if not isinstance(page, dict):
            continue
        imageinfo = page.get("imageinfo")
        if not isinstance(imageinfo, list) or not imageinfo:
            continue
        info = imageinfo[0]
        if not isinstance(info, dict):
            continue
        mime = str(info.get("mime") or "")
        if mime in {"image/svg+xml", "image/gif"}:
            continue
        url = str(info.get("thumburl") or info.get("url") or "")
        if url:
            return url
    return ""


def download_image(session: requests.Session, url: str, size: tuple[int, int]) -> Image.Image | None:
    if not url:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.jpg"
    try:
        if cache_path.exists() and cache_path.stat().st_size > 0:
            raw = cache_path.read_bytes()
        else:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            raw = response.content
            cache_path.write_bytes(raw)
        source = Image.open(BytesIO(raw)).convert("RGB")
        return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    except Exception:
        return None


def draw_fallback(draw: ImageDraw.ImageDraw, kind: str) -> None:
    color = (255, 190, 86) if kind == "food" else (93, 210, 255)
    if kind == "food":
        draw.ellipse((255, 260, 645, 620), fill=(255, 245, 216), outline=color, width=14)
        draw.arc((300, 250, 600, 560), 20, 160, fill=(255, 132, 78), width=18)
        draw.line((315, 645, 585, 645), fill=color, width=16)
    else:
        draw.rounded_rectangle((330, 230, 570, 650), radius=48, fill=(219, 247, 255), outline=color, width=14)
        draw.rectangle((362, 330, 538, 628), fill=(91, 180, 255))
        draw.line((570, 180, 635, 80), fill=color, width=14)
        draw.ellipse((392, 365, 438, 411), fill=(255, 255, 255))


def render_card(item: dict[str, str], kind: str, source: Image.Image | None, output_path: Path = OUTPUT_PATH) -> Path:
    width, height = 900, 900
    image = Image.new("RGB", (width, height), (16, 22, 36))
    draw = ImageDraw.Draw(image)

    if source is not None:
        image.paste(source, (0, 0))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle((0, 0, width, height), fill=(0, 0, 0, 55))
        odraw.rectangle((0, 550, width, height), fill=(5, 10, 22, 205))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
    else:
        for y in range(height):
            ratio = y / max(height - 1, 1)
            top = (32, 45, 76) if kind == "food" else (22, 51, 79)
            bottom = (10, 14, 28)
            color = (
                int(top[0] * (1 - ratio) + bottom[0] * ratio),
                int(top[1] * (1 - ratio) + bottom[1] * ratio),
                int(top[2] * (1 - ratio) + bottom[2] * ratio),
            )
            draw.line((0, y, width, y), fill=color)
        draw_fallback(draw, kind)

    title = "今天吃这个" if kind == "food" else "今天喝这个"
    accent = (255, 204, 96) if kind == "food" else (115, 220, 255)
    draw.rounded_rectangle((56, 56, 344, 114), radius=18, fill=(8, 14, 28), outline=accent, width=3)
    draw.text((78, 70), title, fill=accent, font=FONT_TITLE)

    name = str(item.get("name") or "随便来点好的")
    box = draw.textbbox((0, 0), name, font=FONT_BIG)
    text_w = box[2] - box[0]
    x = max(56, (width - text_w) // 2)
    draw.text((x, 638), name, fill=(255, 255, 255), font=FONT_BIG)
    draw.text((60, 745), "随机推荐，仅供拯救选择困难。", fill=(220, 228, 240), font=FONT_TEXT)
    draw.text((60, 806), "图片来源：Wikimedia Commons；抓取失败时使用本地兜底图。", fill=(170, 184, 205), font=FONT_SMALL)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=88, optimize=True)
    return output_path


def build_random_food_recommendation(kind: str) -> tuple[str, Path, dict[str, Any]]:
    normalized = "drink" if kind == "drink" else "food"
    pool = DRINKS if normalized == "drink" else FOODS
    item = random.choice(pool)
    session = make_session()
    source_image: Image.Image | None = None
    image_url = ""

    try:
        image_url = commons_image_url(session, str(item["query"]))
        source_image = download_image(session, image_url, (900, 900))
    except Exception:
        source_image = None

    image_path = render_card(item, normalized, source_image)
    caption = f"今天{'喝' if normalized == 'drink' else '吃'}：{item['name']}"
    return caption, image_path, {"kind": normalized, **item, "image_url": image_url}


def main() -> int:
    for kind in ("food", "drink"):
        caption, image_path, _item = build_random_food_recommendation(kind)
        print(caption)
        print(f"Image: {image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
