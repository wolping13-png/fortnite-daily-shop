from __future__ import annotations

import hashlib
import random
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "random_food"
OUTPUT_DIR = BASE_DIR / ".cache" / "random_food_output"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"

REQUEST_TIMEOUT = 18
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

FOODS = [
    {"name": "火锅", "query": "hot pot food photo"},
    {"name": "饺子", "query": "jiaozi dumplings food photo"},
    {"name": "牛肉面", "query": "beef noodle soup food photo"},
    {"name": "拉面", "query": "ramen noodles food photo"},
    {"name": "寿司", "query": "sushi food photo"},
    {"name": "披萨", "query": "pizza food photo"},
    {"name": "炸鸡", "query": "fried chicken food photo"},
    {"name": "汉堡", "query": "hamburger food photo"},
    {"name": "烤肉", "query": "barbecue meat food photo"},
    {"name": "炒饭", "query": "fried rice food photo"},
    {"name": "咖喱饭", "query": "curry rice food photo"},
    {"name": "麻辣烫", "query": "malatang food photo"},
    {"name": "烤鱼", "query": "grilled fish food photo"},
    {"name": "螺蛳粉", "query": "luosifen food photo"},
    {"name": "黄焖鸡米饭", "query": "braised chicken rice food photo"},
    {"name": "煲仔饭", "query": "claypot rice food photo"},
    {"name": "盖浇饭", "query": "rice bowl food photo"},
    {"name": "小笼包", "query": "xiaolongbao food photo"},
    {"name": "三明治", "query": "sandwich food photo"},
    {"name": "意大利面", "query": "spaghetti pasta food photo"},
    {"name": "日式便当", "query": "bento food photo"},
    {"name": "墨西哥卷饼", "query": "tacos food photo"},
]

DRINKS = [
    {"name": "珍珠奶茶", "query": "bubble tea drink photo"},
    {"name": "冰美式", "query": "iced americano coffee photo"},
    {"name": "拿铁", "query": "latte coffee drink photo"},
    {"name": "柠檬茶", "query": "lemon iced tea drink photo"},
    {"name": "椰子水", "query": "coconut water drink photo"},
    {"name": "橙汁", "query": "orange juice drink photo"},
    {"name": "酸梅汤", "query": "suanmeitang drink photo"},
    {"name": "可乐", "query": "cola drink glass photo"},
    {"name": "热巧克力", "query": "hot chocolate drink photo"},
    {"name": "抹茶拿铁", "query": "matcha latte drink photo"},
    {"name": "乌龙茶", "query": "oolong tea drink photo"},
    {"name": "茉莉花茶", "query": "jasmine tea drink photo"},
    {"name": "豆浆", "query": "soy milk drink photo"},
    {"name": "气泡水", "query": "sparkling water drink photo"},
    {"name": "芒果冰沙", "query": "mango smoothie drink photo"},
    {"name": "草莓奶昔", "query": "strawberry milkshake drink photo"},
    {"name": "西瓜汁", "query": "watermelon juice drink photo"},
    {"name": "姜汁汽水", "query": "ginger ale drink photo"},
]


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def commons_image_urls(session: requests.Session, query: str, limit: int = 8) -> list[str]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": query,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": 1200,
    }
    response = session.get(COMMONS_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return []

    urls: list[str] = []
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
            urls.append(url)
    random.shuffle(urls)
    return urls


def save_real_photo(session: requests.Session, url: str, output_path: Path) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.img"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        raw = cache_path.read_bytes()
    else:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        raw = response.content
        cache_path.write_bytes(raw)

    image = Image.open(BytesIO(raw)).convert("RGB")
    if image.width < 160 or image.height < 160:
        raise ValueError("Image is too small.")

    image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    image.save(output_path, quality=90, optimize=True)
    return output_path


def build_random_food_recommendation(kind: str) -> tuple[str, Path, dict[str, Any]]:
    normalized = "drink" if kind == "drink" else "food"
    pool = DRINKS if normalized == "drink" else FOODS
    session = make_session()
    candidates = random.sample(pool, k=len(pool))
    errors: list[str] = []

    for item in candidates:
        urls = commons_image_urls(session, str(item["query"]))
        for url in urls:
            try:
                key = hashlib.sha1(f"{normalized}:{item['name']}:{url}".encode("utf-8")).hexdigest()[:12]
                image_path = OUTPUT_DIR / f"random_{normalized}_{key}.jpg"
                save_real_photo(session, url, image_path)
                caption = f"今天{'喝' if normalized == 'drink' else '吃'}：{item['name']}"
                return caption, image_path, {"kind": normalized, **item, "image_url": url}
            except Exception as exc:
                errors.append(f"{item['name']}: {exc}")
                continue

    raise RuntimeError("没有找到可发送的实物图片。")


def main() -> int:
    for kind in ("food", "drink"):
        caption, image_path, _item = build_random_food_recommendation(kind)
        print(caption)
        print(f"Image: {image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
