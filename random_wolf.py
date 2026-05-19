from __future__ import annotations

import hashlib
import random
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "random_wolf"
OUTPUT_DIR = BASE_DIR / ".cache" / "random_wolf_output"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

REQUEST_TIMEOUT = 18
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

WOLF_QUERIES = [
    "cute wolf photo",
    "gray wolf close up photo",
    "wolf pup photo",
    "young wolf photo",
    "wolf in snow photo",
    "canis lupus portrait photo",
    "wolf wildlife photography",
    "cute grey wolf animal photo",
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


def commons_image_urls(session: requests.Session, query: str, limit: int = 10) -> list[str]:
    response = session.get(
        COMMONS_API_URL,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": query,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": 1400,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return []

    urls: list[str] = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "").lower()
        if any(word in title for word in ("logo", "map", "svg", "diagram", "drawing", "sign")):
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


def tavily_image_urls(session: requests.Session, api_key: str, query: str, limit: int = 10) -> list[str]:
    api_key = api_key.strip()
    if not api_key:
        return []

    response = session.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": f"{query} real wolf wildlife photo cute",
            "topic": "general",
            "search_depth": "basic",
            "max_results": 3,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": True,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    urls: list[str] = []

    images = data.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, str):
                urls.append(image)
            elif isinstance(image, dict) and image.get("url"):
                urls.append(str(image["url"]))

    results = data.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict):
                continue
            result_images = result.get("images")
            if not isinstance(result_images, list):
                continue
            for image in result_images:
                if isinstance(image, str):
                    urls.append(image)
                elif isinstance(image, dict) and image.get("url"):
                    urls.append(str(image["url"]))

    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in urls:
        lower = url.lower()
        if url and url not in seen and not lower.endswith((".svg", ".gif")):
            seen.add(url)
            unique_urls.append(url)
    random.shuffle(unique_urls)
    return unique_urls[:limit]


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
    if image.width < 220 or image.height < 220:
        raise ValueError("Image is too small.")

    image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=90, optimize=True)
    return output_path


def build_random_wolf(tavily_api_key: str = "") -> tuple[str, Path, dict[str, Any]]:
    session = make_session()
    queries = random.sample(WOLF_QUERIES, k=len(WOLF_QUERIES))
    errors: list[str] = []

    for query in queries:
        urls: list[str] = []
        try:
            urls.extend(commons_image_urls(session, query))
        except Exception as exc:
            errors.append(f"Wikimedia {query}: {exc}")

        if not urls:
            try:
                urls.extend(tavily_image_urls(session, tavily_api_key, query))
            except Exception as exc:
                errors.append(f"Tavily {query}: {exc}")

        for url in urls:
            try:
                key = hashlib.sha1(f"wolf:{query}:{url}".encode("utf-8")).hexdigest()[:12]
                image_path = OUTPUT_DIR / f"wolf_{key}.jpg"
                save_real_photo(session, url, image_path)
                return "狼狼来啦", image_path, {"query": query, "image_url": url}
            except Exception as exc:
                errors.append(f"{query}: {exc}")
                continue

    detail = "；".join(errors[:5])
    raise RuntimeError(f"没有找到可发送的狼图。{detail}")


def main() -> int:
    caption, image_path, item = build_random_wolf()
    print(caption)
    print(image_path)
    print(item.get("image_url", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
