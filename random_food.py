from __future__ import annotations

import hashlib
import json
import random
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "random_food"
OUTPUT_DIR = BASE_DIR / ".cache" / "random_food_output"
HISTORY_PATH = CACHE_DIR / "history.json"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

REQUEST_TIMEOUT = 10
RECENT_ITEM_LIMITS = {"food": 12, "drink": 9}
RECENT_IMAGE_LIMIT = 100
CACHED_IMAGE_LIMIT_PER_ITEM = 5
MAX_ITEM_ATTEMPTS = 7
OUTPUT_IMAGE_MAX_SIZE = 960
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

ITEM_TERMS = {
    "火锅": ("hot pot", "hotpot", "huoguo", "火锅"),
    "饺子": ("jiaozi", "dumpling", "dumplings", "gyoza", "饺子"),
    "牛肉面": ("beef noodle", "beef noodles", "beef noodle soup", "牛肉面"),
    "拉面": ("ramen", "拉面"),
    "寿司": ("sushi", "寿司"),
    "披萨": ("pizza", "pizzas", "披萨"),
    "炸鸡": ("fried chicken", "crispy chicken", "炸鸡"),
    "汉堡": ("hamburger", "burger", "汉堡"),
    "烤肉": ("barbecue", "bbq", "grilled meat", "korean barbecue", "烤肉"),
    "炒饭": ("fried rice", "炒饭"),
    "咖喱饭": ("curry rice", "kare raisu", "咖喱饭"),
    "麻辣烫": ("malatang", "麻辣烫"),
    "烤鱼": ("grilled fish", "roast fish", "烤鱼"),
    "螺蛳粉": ("luosifen", "river snail rice noodle", "螺蛳粉"),
    "黄焖鸡米饭": ("braised chicken rice", "huangmenji", "黄焖鸡"),
    "煲仔饭": ("claypot rice", "clay pot rice", "煲仔饭"),
    "盖浇饭": ("rice bowl", "donburi", "盖浇饭"),
    "小笼包": ("xiaolongbao", "xiao long bao", "soup dumpling", "小笼包"),
    "三明治": ("sandwich", "三明治"),
    "意大利面": ("spaghetti", "pasta", "意大利面"),
    "日式便当": ("bento", "bento box", "便当"),
    "墨西哥卷饼": ("burrito", "taco", "tacos", "mexican wrap", "墨西哥卷饼"),
    "珍珠奶茶": ("bubble tea", "boba tea", "boba milk tea", "珍珠奶茶"),
    "冰美式": ("iced americano", "americano coffee", "冰美式"),
    "拿铁": ("latte", "caffe latte", "拿铁"),
    "柠檬茶": ("lemon tea", "iced lemon tea", "柠檬茶"),
    "椰子水": ("coconut water", "椰子水"),
    "橙汁": ("orange juice", "橙汁"),
    "酸梅汤": ("suanmeitang", "sour plum drink", "酸梅汤"),
    "可乐": ("cola", "coke", "coca cola", "可乐"),
    "热巧克力": ("hot chocolate", "cocoa drink", "热巧克力"),
    "抹茶拿铁": ("matcha latte", "抹茶拿铁"),
    "乌龙茶": ("oolong tea", "乌龙茶"),
    "茉莉花茶": ("jasmine tea", "茉莉花茶"),
    "豆浆": ("soy milk", "soya milk", "豆浆"),
    "气泡水": ("sparkling water", "soda water", "气泡水"),
    "芒果冰沙": ("mango smoothie", "mango shake", "芒果冰沙"),
    "草莓奶昔": ("strawberry milkshake", "strawberry shake", "草莓奶昔"),
    "西瓜汁": ("watermelon juice", "西瓜汁"),
    "姜汁汽水": ("ginger ale", "ginger soda", "姜汁汽水"),
}

BAD_IMAGE_TERMS = (
    "logo",
    "icon",
    "clipart",
    "illustration",
    "drawing",
    "cartoon",
    "emoji",
    "sticker",
    "vector",
    "map",
    "menu",
    "poster",
    "advertisement",
    "infographic",
    "packaging",
    "package",
    "brand",
)

BAD_IMAGE_URL_TERMS = (
    "logo",
    "icon",
    "sprite",
    "favicon",
    "placeholder",
    "avatar",
    "brand",
    "watermark",
    "trip.com",
    "tripcdn",
    "ctrip",
)

BAD_SOURCE_DOMAINS = (
    "trip.com",
    "tripcdn.com",
    "ctrip.com",
    "booking.com",
    "expedia.com",
    "agoda.com",
    "hotels.com",
)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def normalize_match_text(value: str) -> str:
    text = unquote(value).lower()
    text = re.sub(r"https?://", " ", text)
    text = re.sub(r"[_%+./?#=&:;|()[\]{}-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def image_fingerprint(url: str) -> str:
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()


def load_history() -> dict[str, Any]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_history(history: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def recent_bucket(history: dict[str, Any], kind: str) -> dict[str, Any]:
    bucket = history.get(kind)
    if not isinstance(bucket, dict):
        bucket = {}
        history[kind] = bucket
    bucket.setdefault("items", [])
    bucket.setdefault("images", [])
    bucket.setdefault("item_images", {})
    return bucket


def update_history(
    history: dict[str, Any],
    kind: str,
    item_name: str,
    image_url: str,
    candidate: dict[str, Any] | None = None,
) -> None:
    bucket = recent_bucket(history, kind)

    items = [str(value) for value in bucket.get("items", []) if str(value) != item_name]
    items.insert(0, item_name)
    bucket["items"] = items[: RECENT_ITEM_LIMITS.get(kind, 10)]

    image_key = image_fingerprint(image_url)
    images = [str(value) for value in bucket.get("images", []) if str(value) != image_key]
    images.insert(0, image_key)
    bucket["images"] = images[:RECENT_IMAGE_LIMIT]

    item_images = bucket.get("item_images")
    if not isinstance(item_images, dict):
        item_images = {}
        bucket["item_images"] = item_images
    existing = item_images.get(item_name)
    if not isinstance(existing, list):
        existing = []
    source = str((candidate or {}).get("source") or "unknown")
    title = str((candidate or {}).get("title") or (candidate or {}).get("source_title") or item_name)
    entries = [entry for entry in existing if isinstance(entry, dict) and str(entry.get("url") or "") != image_url]
    entries.insert(
        0,
        {
            "url": image_url,
            "source": source,
            "title": title[:160],
            "saved_at": int(time.time()),
        },
    )
    item_images[item_name] = entries[:CACHED_IMAGE_LIMIT_PER_ITEM]
    bucket["updated_at"] = int(time.time())

    save_history(history)


def item_terms(item: dict[str, Any]) -> tuple[str, ...]:
    name = str(item.get("name") or "")
    terms = list(ITEM_TERMS.get(name, ()))
    terms.append(name)
    query = str(item.get("query") or "")
    if query:
        terms.append(query.replace(" photo", "").replace(" food", "").replace(" drink", "").strip())
    return tuple(dict.fromkeys(term.strip().lower() for term in terms if term.strip()))


def candidate_text(candidate: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("title", "description", "source_title", "source_content", "source_url", "url"):
        value = candidate.get(key)
        if value:
            values.append(str(value))
    return normalize_match_text(" ".join(values))


def is_bad_url_value(value: str) -> bool:
    raw = unquote(str(value or "")).lower()
    if not raw:
        return False
    normalized = normalize_match_text(raw)
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if any(host == domain or host.endswith(f".{domain}") for domain in BAD_SOURCE_DOMAINS):
        return True
    return any(term in raw or normalize_match_text(term) in normalized for term in BAD_IMAGE_URL_TERMS)


def candidate_has_bad_image_reference(candidate: dict[str, Any]) -> bool:
    for key in ("url", "source_url"):
        value = str(candidate.get(key) or "").strip()
        if value and is_bad_url_value(value):
            return True
    return False


def candidate_match_score(candidate: dict[str, Any], item: dict[str, Any]) -> int:
    if candidate_has_bad_image_reference(candidate):
        return 0
    if candidate.get("trusted_match"):
        return 100

    text = candidate_text(candidate)
    if not text:
        return 0
    if any(term in text for term in BAD_IMAGE_TERMS):
        return 0

    score = 0
    for term in item_terms(item):
        normalized = normalize_match_text(term)
        if not normalized:
            continue
        if normalized in text:
            score += 6 if (" " in normalized or len(normalized) >= 5) else 3

    title = normalize_match_text(str(candidate.get("title") or ""))
    source_title = normalize_match_text(str(candidate.get("source_title") or ""))
    name = normalize_match_text(str(item.get("name") or ""))
    if name and (name in title or name in source_title):
        score += 8

    if str(candidate.get("source") or "").startswith("tavily"):
        score += 1
    return score if score >= 5 else 0


def candidate_matches_item(candidate: dict[str, Any], item: dict[str, Any]) -> bool:
    return candidate_match_score(candidate, item) > 0


def ranked_matching_candidates(candidates: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
    shuffled = dedupe_candidates(candidates)
    random.shuffle(shuffled)
    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in shuffled:
        score = candidate_match_score(candidate, item)
        if score:
            scored.append((score, candidate))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _score, candidate in scored]


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url or url in seen or candidate_has_bad_image_reference(candidate):
            continue
        seen.add(url)
        unique.append(candidate)
    return unique


def ordered_items(pool: list[dict[str, Any]], kind: str, history: dict[str, Any]) -> list[dict[str, Any]]:
    recent_items = set(str(value) for value in recent_bucket(history, kind).get("items", []))
    fresh = [item for item in pool if str(item.get("name") or "") not in recent_items]
    if len(fresh) >= max(4, len(pool) // 3):
        candidates = fresh
    else:
        candidates = pool
    return random.sample(candidates, k=len(candidates))


def cached_image_candidates(history: dict[str, Any], kind: str, item: dict[str, Any]) -> list[dict[str, Any]]:
    bucket = recent_bucket(history, kind)
    item_images = bucket.get("item_images")
    if not isinstance(item_images, dict):
        return []

    name = str(item.get("name") or "")
    entries = item_images.get(name)
    if not isinstance(entries, list):
        return []

    candidates: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        candidates.append(
            {
                "url": url,
                "title": str(entry.get("title") or name),
                "description": name,
                "source": f"cache:{entry.get('source') or 'unknown'}",
                "trusted_match": True,
            }
        )
    return candidates


def commons_image_candidates(session: requests.Session, query: str, limit: int = 8) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": query,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 1200,
    }
    response = session.get(COMMONS_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return []

    candidates: list[dict[str, Any]] = []
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
            candidates.append(
                {
                    "url": url,
                    "title": str(page.get("title") or ""),
                    "description": str(info.get("extmetadata", {}) or ""),
                    "source": "wikimedia",
                }
            )
    candidates = dedupe_candidates(candidates)
    random.shuffle(candidates)
    return candidates


def tavily_image_candidates(session: requests.Session, api_key: str, item: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    api_key = api_key.strip()
    if not api_key:
        return []

    name = str(item.get("name") or "")
    query = str(item.get("query") or name)
    terms = [term for term in item_terms(item) if re.search(r"[a-zA-Z]", term)]
    primary_term = terms[0] if terms else query
    search_query = (
        f'"{primary_term}" "{name}" real food photo actual dish close-up '
        f'-logo -icon -cartoon -illustration -menu -poster -packaging'
    )
    if any(word in query for word in ("drink", "coffee", "tea", "juice", "smoothie", "cola", "latte")):
        search_query = (
            f'"{primary_term}" "{name}" real drink photo actual beverage close-up '
            f'-logo -icon -cartoon -illustration -menu -poster -packaging'
        )

    response = session.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": search_query,
            "topic": "general",
            "search_depth": "basic",
            "max_results": 4,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": True,
            "include_image_descriptions": True,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    candidates: list[dict[str, Any]] = []

    images = data.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, str):
                candidates.append({"url": image, "title": "", "description": "", "source": "tavily"})
            elif isinstance(image, dict) and image.get("url"):
                candidates.append(
                    {
                        "url": str(image["url"]),
                        "title": str(image.get("title") or image.get("alt") or ""),
                        "description": str(image.get("description") or ""),
                        "source": "tavily",
                    }
                )

    results = data.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict):
                continue
            result_images = result.get("images")
            if not isinstance(result_images, list):
                continue
            for image in result_images:
                base = {
                    "source_title": str(result.get("title") or ""),
                    "source_content": str(result.get("content") or ""),
                    "source_url": str(result.get("url") or ""),
                    "source": "tavily-result",
                }
                if isinstance(image, str):
                    candidates.append({"url": image, "title": "", "description": "", **base})
                elif isinstance(image, dict) and image.get("url"):
                    candidates.append(
                        {
                            "url": str(image["url"]),
                            "title": str(image.get("title") or image.get("alt") or ""),
                            "description": str(image.get("description") or ""),
                            **base,
                        }
                    )

    candidates = dedupe_candidates(candidates)
    random.shuffle(candidates)
    return candidates


def save_real_photo(session: requests.Session, url: str, output_path: Path) -> Path:
    if is_bad_url_value(url):
        raise ValueError("Blocked logo/travel-site image URL.")

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

    image.thumbnail((OUTPUT_IMAGE_MAX_SIZE, OUTPUT_IMAGE_MAX_SIZE), Image.Resampling.LANCZOS)
    image.save(output_path, quality=84, optimize=True)
    return output_path


def build_random_food_recommendation(kind: str, tavily_api_key: str = "") -> tuple[str, Path, dict[str, Any]]:
    normalized = "drink" if kind == "drink" else "food"
    pool = DRINKS if normalized == "drink" else FOODS
    session = make_session()
    history = load_history()
    candidates = ordered_items(pool, normalized, history)
    recent_images = set(str(value) for value in recent_bucket(history, normalized).get("images", []))
    errors: list[str] = []

    for item in candidates[:MAX_ITEM_ATTEMPTS]:
        image_candidates: list[dict[str, Any]] = []

        cached = ranked_matching_candidates(cached_image_candidates(history, normalized, item), item)
        for candidate in cached:
            url = str(candidate.get("url") or "").strip()
            if not url or image_fingerprint(url) in recent_images:
                continue
            try:
                key = hashlib.sha1(f"{normalized}:{item['name']}:{url}".encode("utf-8")).hexdigest()[:12]
                image_path = OUTPUT_DIR / f"random_{normalized}_{key}.jpg"
                save_real_photo(session, url, image_path)
                caption = f"今天{'喝' if normalized == 'drink' else '吃'}：{item['name']}"
                update_history(history, normalized, str(item["name"]), url, candidate)
                return caption, image_path, {"kind": normalized, **item, "image_url": url, "source": "cache"}
            except Exception as exc:
                errors.append(f"{item['name']} cache: {exc}")

        try:
            image_candidates.extend(tavily_image_candidates(session, tavily_api_key, item, limit=6))
        except Exception as exc:
            errors.append(f"{item['name']} Tavily: {exc}")

        matched = ranked_matching_candidates(image_candidates, item)

        if not matched:
            try:
                image_candidates.extend(commons_image_candidates(session, str(item["query"]), limit=6))
            except Exception as exc:
                errors.append(f"{item['name']} Wikimedia: {exc}")

        matched = ranked_matching_candidates(image_candidates, item)

        for candidate in matched:
            url = str(candidate.get("url") or "").strip()
            if not url or image_fingerprint(url) in recent_images:
                continue
            try:
                key = hashlib.sha1(f"{normalized}:{item['name']}:{url}".encode("utf-8")).hexdigest()[:12]
                image_path = OUTPUT_DIR / f"random_{normalized}_{key}.jpg"
                save_real_photo(session, url, image_path)
                caption = f"今天{'喝' if normalized == 'drink' else '吃'}：{item['name']}"
                update_history(history, normalized, str(item["name"]), url, candidate)
                return caption, image_path, {"kind": normalized, **item, "image_url": url, "source": candidate.get("source")}
            except Exception as exc:
                errors.append(f"{item['name']}: {exc}")
                continue

    detail = "；".join(errors[:5])
    raise RuntimeError(f"没有找到可发送的实物图片。{detail}")


def main() -> int:
    for kind in ("food", "drink"):
        caption, image_path, _item = build_random_food_recommendation(kind)
        print(caption)
        print(f"Image: {image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
