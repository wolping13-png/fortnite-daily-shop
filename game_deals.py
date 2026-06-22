from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_JSON_PATH = BASE_DIR / "game_deals.json"
OUTPUT_IMAGE_PATH = BASE_DIR / "game_deals.jpg"
CACHE_DIR = BASE_DIR / ".cache" / "game_deals"

STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
EPIC_FREE_GAMES_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"

REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

WIDTH = 1080
PADDING = 42
GAP = 18
BG_TOP = (11, 18, 35)
BG_BOTTOM = (5, 8, 18)
PANEL = (22, 31, 52)
PANEL_2 = (27, 40, 68)
LINE = (74, 96, 137)
TEXT = (245, 248, 255)
MUTED = (172, 185, 205)
GREEN = (85, 238, 151)
YELLOW = (255, 212, 74)
BLUE = (96, 167, 255)
RED = (255, 93, 105)


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


FONT_TITLE = load_font(42, True)
FONT_SUBTITLE = load_font(21, False)
FONT_SECTION = load_font(28, True)
FONT_CARD_TITLE = load_font(21, True)
FONT_CARD_TEXT = load_font(17, False)
FONT_SMALL = load_font(15, False)
FONT_BADGE = load_font(17, True)

STEAM_CARD_H = 156
EPIC_CARD_H = 236


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


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    source = str(text or "").replace("\n", " ").strip()
    if not source:
        return [""]

    tokens = source.split() if " " in source else list(source)
    lines: list[str] = []
    current = ""
    for token in tokens:
        joiner = " " if " " in source and current else ""
        attempt = f"{current}{joiner}{token}"
        if text_size(draw, attempt, font)[0] <= max_width:
            current = attempt
            continue
        if current:
            lines.append(current)
        current = token
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and text_size(draw, lines[-1], font)[0] > max_width:
        lines[-1] = fit_text(draw, lines[-1], font, max_width)
    if len(lines) == max_lines and "".join(lines) != source.replace(" ", ""):
        lines[-1] = fit_text(draw, lines[-1] + "...", font, max_width)
    return lines


def strip_tags(value: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_first(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return html.unescape(match.group(1)).strip() if match else default


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def fetch_steam_top_discounted(session: requests.Session, limit: int = 12) -> list[dict[str, Any]]:
    params = {
        "query": "",
        "start": 0,
        "count": max(limit * 2, 24),
        "dynamic_data": "",
        "sort_by": "_ASC",
        "filter": "topsellers",
        "specials": 1,
        "infinite": 1,
        "cc": "cn",
        "l": "schinese",
    }
    response = session.get(STEAM_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    results_html = str(data.get("results_html") or "")
    rows = re.findall(
        r'(<a[^>]+class="[^"]*search_result_row[^"]*"[\s\S]*?</a>)',
        results_html,
        flags=re.I,
    )

    deals: list[dict[str, Any]] = []
    for row in rows:
        title = strip_tags(extract_first(r'<span[^>]+class="[^"]*title[^"]*"[^>]*>(.*?)</span>', row))
        if not title:
            continue
        discount = strip_tags(extract_first(r'<div[^>]+class="[^"]*discount_pct[^"]*"[^>]*>(.*?)</div>', row))
        if not discount or discount in {"", "0%"}:
            continue
        final_price = strip_tags(
            extract_first(r'<div[^>]+class="[^"]*discount_final_price[^"]*"[^>]*>(.*?)</div>', row)
        )
        original_price = strip_tags(
            extract_first(r'<div[^>]+class="[^"]*discount_original_price[^"]*"[^>]*>(.*?)</div>', row)
        )
        image_url = extract_first(r'<img[^>]+src="([^"]+)"', row)
        href = extract_first(r'href="([^"]+)"', row)
        appid = extract_first(r'data-ds-appid="([^"]+)"', row) or extract_first(r'data-ds-bundleid="([^"]+)"', row)
        release = strip_tags(
            extract_first(r'<div[^>]+class="[^"]*search_released[^"]*"[^>]*>(.*?)</div>', row)
        )
        deals.append(
            {
                "platform": "Steam",
                "rank": len(deals) + 1,
                "id": appid,
                "title": title,
                "discount": discount,
                "final_price": final_price or "价格未知",
                "original_price": original_price,
                "release": release,
                "image": image_url,
                "url": href,
            }
        )
        if len(deals) >= limit:
            break
    return deals


def parse_epic_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_time(value: datetime | None) -> str:
    if not value:
        return "时间未知"
    local = value.astimezone()
    return local.strftime("%m-%d %H:%M")


def select_epic_image(item: dict[str, Any]) -> str:
    images = item.get("keyImages")
    if not isinstance(images, list):
        return ""
    preferred = (
        "DieselStoreFrontWide",
        "OfferImageWide",
        "VaultClosed",
        "Thumbnail",
        "DieselGameBoxTall",
        "OfferImageTall",
    )
    for image_type in preferred:
        for image in images:
            if isinstance(image, dict) and image.get("type") == image_type and image.get("url"):
                return str(image["url"])
    for image in images:
        if isinstance(image, dict) and image.get("url"):
            return str(image["url"])
    return ""


def epic_url(item: dict[str, Any]) -> str:
    mappings = item.get("catalogNs", {}).get("mappings")
    slug = ""
    if isinstance(mappings, list) and mappings:
        first = mappings[0]
        if isinstance(first, dict):
            slug = str(first.get("pageSlug") or "").strip("/")
    slug = slug or str(item.get("productSlug") or item.get("urlSlug") or "").strip("/")
    return f"https://store.epicgames.com/zh-CN/p/{slug}" if slug else "https://store.epicgames.com/zh-CN/free-games"


def epic_price(item: dict[str, Any]) -> str:
    price = item.get("price")
    if not isinstance(price, dict):
        return "原价未知"
    total = price.get("totalPrice")
    if not isinstance(total, dict):
        return "原价未知"
    fmt = total.get("fmtPrice")
    if isinstance(fmt, dict):
        return str(fmt.get("originalPrice") or fmt.get("discountPrice") or "原价未知")
    original = total.get("originalPrice")
    if isinstance(original, int):
        return f"¥{original / 100:.2f}"
    return "原价未知"


def collect_epic_promo(item: dict[str, Any], now: datetime) -> tuple[str, datetime | None, datetime | None] | None:
    promotions = item.get("promotions")
    if not isinstance(promotions, dict):
        return None

    for promo_group in promotions.get("promotionalOffers") or []:
        if not isinstance(promo_group, dict):
            continue
        for promo in promo_group.get("promotionalOffers") or []:
            if not isinstance(promo, dict):
                continue
            if promo.get("discountSetting", {}).get("discountPercentage") != 0:
                continue
            start = parse_epic_time(promo.get("startDate"))
            end = parse_epic_time(promo.get("endDate"))
            if start and end and start <= now <= end:
                return "current", start, end

    for promo_group in promotions.get("upcomingPromotionalOffers") or []:
        if not isinstance(promo_group, dict):
            continue
        for promo in promo_group.get("promotionalOffers") or []:
            if not isinstance(promo, dict):
                continue
            if promo.get("discountSetting", {}).get("discountPercentage") != 0:
                continue
            start = parse_epic_time(promo.get("startDate"))
            end = parse_epic_time(promo.get("endDate"))
            if start and start > now:
                return "upcoming", start, end

    return None


def fetch_epic_free_games(session: requests.Session, country: str = "CN") -> dict[str, list[dict[str, Any]]]:
    params = {
        "locale": "zh-CN",
        "country": country,
        "allowCountries": country,
    }
    response = session.get(EPIC_FREE_GAMES_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
    now = datetime.now(timezone.utc)
    result: dict[str, list[dict[str, Any]]] = {"current": [], "upcoming": []}

    if not isinstance(elements, list):
        return result

    seen: set[str] = set()
    for item in elements:
        if not isinstance(item, dict):
            continue
        promo = collect_epic_promo(item, now)
        if not promo:
            continue
        status, start, end = promo
        title = str(item.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        result[status].append(
            {
                "platform": "Epic",
                "status": status,
                "title": title,
                "description": str(item.get("description") or "").strip(),
                "original_price": epic_price(item),
                "start": start.isoformat() if start else "",
                "end": end.isoformat() if end else "",
                "start_text": format_time(start),
                "end_text": format_time(end),
                "image": select_epic_image(item),
                "url": epic_url(item),
            }
        )

    result["current"].sort(key=lambda item: item.get("end") or "")
    result["upcoming"].sort(key=lambda item: item.get("start") or "")
    return result


def fetch_game_deals(steam_limit: int = 12, epic_country: str = "CN") -> dict[str, Any]:
    session = make_session()
    data: dict[str, Any] = {
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steam": [],
        "epic": {"current": [], "upcoming": []},
        "errors": [],
    }

    try:
        data["steam"] = fetch_steam_top_discounted(session, limit=steam_limit)
    except Exception as exc:
        data["errors"].append(f"Steam: {exc}")

    try:
        epic = fetch_epic_free_games(session, country=epic_country)
        if epic_country.upper() != "US" and not epic["current"] and not epic["upcoming"]:
            epic = fetch_epic_free_games(session, country="US")
        data["epic"] = epic
    except Exception as exc:
        data["errors"].append(f"Epic: {exc}")

    OUTPUT_JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def download_image(session: requests.Session, url: str, size: tuple[int, int]) -> Image.Image:
    if not url:
        return placeholder(size)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".jpg"
    cache_path = CACHE_DIR / f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}{suffix}"
    try:
        if cache_path.exists() and cache_path.stat().st_size > 0:
            raw = cache_path.read_bytes()
        else:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            raw = response.content
            cache_path.write_bytes(raw)
        image = Image.open(BytesIO(raw)).convert("RGB")
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    except Exception:
        return placeholder(size)


def placeholder(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, (35, 48, 77))
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        ratio = y / max(size[1] - 1, 1)
        color = (
            int(41 * (1 - ratio) + 16 * ratio),
            int(67 * (1 - ratio) + 28 * ratio),
            int(116 * (1 - ratio) + 64 * ratio),
        )
        draw.line((0, y, size[0], y), fill=color)
    draw.text((size[0] // 2, size[1] // 2), "GAME", fill=MUTED, font=FONT_SECTION, anchor="mm")
    return image


def rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: tuple[int, int, int], outline: tuple[int, int, int] | None = None, radius: int = 10, width: int = 1) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill: tuple[int, int, int]) -> int:
    tw, th = text_size(draw, text, FONT_BADGE)
    w = tw + 22
    h = 30
    rounded_rect(draw, (x, y, x + w, y + h), fill=fill, radius=8)
    draw.text((x + 11, y + 5), text, fill=(7, 13, 26), font=FONT_BADGE)
    return w


def draw_header(draw: ImageDraw.ImageDraw, data: dict[str, Any]) -> int:
    y = 34
    draw.text((PADDING, y), "每日游戏优惠情报", fill=TEXT, font=FONT_TITLE)
    updated = str(data.get("updatedAt") or "")[:16].replace("T", " ")
    subtitle = f"Steam 高销量折扣榜 + Epic 喜加一 · {updated}"
    draw.text((PADDING, y + 58), subtitle, fill=MUTED, font=FONT_SUBTITLE)
    return 130


def draw_section_title(draw: ImageDraw.ImageDraw, y: int, title: str, subtitle: str = "") -> int:
    draw.text((PADDING, y), title, fill=TEXT, font=FONT_SECTION)
    if subtitle:
        draw.text((PADDING, y + 36), subtitle, fill=MUTED, font=FONT_SMALL)
        return y + 70
    return y + 48


def draw_steam_card(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    session: requests.Session,
    deal: dict[str, Any],
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    rounded_rect(draw, (x, y, x + w, y + h), fill=PANEL, outline=LINE, radius=12)
    thumb_w = 168
    thumb_h = h - 22
    thumb = download_image(session, str(deal.get("image") or ""), (thumb_w, thumb_h))
    image.paste(thumb, (x + 11, y + 11))

    tx = x + 192
    rank = int(deal.get("rank") or 0)
    draw.text((tx, y + 14), f"#{rank}", fill=BLUE, font=FONT_BADGE)
    draw_badge(draw, x + w - 92, y + 12, str(deal.get("discount") or "-"), GREEN)

    content_w = w - 220
    title_lines = wrap_text(draw, str(deal.get("title") or "未知游戏"), FONT_CARD_TITLE, content_w, 2)
    line_y = y + 44
    for line in title_lines:
        draw.text((tx, line_y), line, fill=TEXT, font=FONT_CARD_TITLE)
        line_y += 26

    final_price = str(deal.get("final_price") or "价格未知")
    original_price = str(deal.get("original_price") or "")
    price_y = max(line_y + 6, y + h - 58)
    final_price = fit_text(draw, final_price, FONT_CARD_TITLE, content_w)
    draw.text((tx, price_y), final_price, fill=YELLOW, font=FONT_CARD_TITLE)
    if original_price:
        original_text = fit_text(draw, f"原价 {original_price}", FONT_SMALL, content_w)
        draw.text((tx, price_y + 27), original_text, fill=MUTED, font=FONT_SMALL)


def draw_epic_card(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    session: requests.Session,
    item: dict[str, Any],
    x: int,
    y: int,
    w: int,
    h: int,
    current: bool,
) -> None:
    rounded_rect(draw, (x, y, x + w, y + h), fill=PANEL_2, outline=LINE, radius=12)
    thumb_h = 132
    thumb = download_image(session, str(item.get("image") or ""), (w - 22, thumb_h))
    image.paste(thumb, (x + 11, y + 11))

    badge_text = "正在免费" if current else "即将免费"
    draw_badge(draw, x + 20, y + 22, badge_text, GREEN if current else YELLOW)

    title_lines = wrap_text(draw, str(item.get("title") or "未知游戏"), FONT_CARD_TITLE, w - 34, 2)
    line_y = y + 158
    for line in title_lines:
        draw.text((x + 17, line_y), line, fill=TEXT, font=FONT_CARD_TITLE)
        line_y += 27

    price = str(item.get("original_price") or "原价未知")
    time_label = f"截止 {item.get('end_text')}" if current else f"开始 {item.get('start_text')}"
    draw.text((x + 17, y + h - 58), f"原价 {price}", fill=MUTED, font=FONT_SMALL)
    draw.text((x + 17, y + h - 31), time_label, fill=YELLOW if current else BLUE, font=FONT_CARD_TEXT)


def render_game_deals_image(data: dict[str, Any], output_path: Path = OUTPUT_IMAGE_PATH) -> Path:
    steam = data.get("steam") if isinstance(data.get("steam"), list) else []
    epic = data.get("epic") if isinstance(data.get("epic"), dict) else {}
    epic_current = epic.get("current") if isinstance(epic.get("current"), list) else []
    epic_upcoming = epic.get("upcoming") if isinstance(epic.get("upcoming"), list) else []

    steam_rows = max(1, (min(len(steam), 12) + 1) // 2)
    epic_count = min(len(epic_current) + len(epic_upcoming), 4)
    epic_rows = max(1, (epic_count + 1) // 2)

    height = (
        150
        + 74
        + steam_rows * (STEAM_CARD_H + GAP)
        + 38
        + 74
        + epic_rows * (EPIC_CARD_H + GAP)
        + 70
    )
    image = Image.new("RGB", (WIDTH, height), BG_BOTTOM)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(BG_TOP[0] * (1 - ratio) + BG_BOTTOM[0] * ratio),
            int(BG_TOP[1] * (1 - ratio) + BG_BOTTOM[1] * ratio),
            int(BG_TOP[2] * (1 - ratio) + BG_BOTTOM[2] * ratio),
        )
        draw.line((0, y, WIDTH, y), fill=color)

    session = make_session()
    y = draw_header(draw, data)
    y = draw_section_title(draw, y, "Steam 高销量折扣榜", "按 Steam 商店热销折扣结果排序，取前 12 个")

    card_w = (WIDTH - PADDING * 2 - GAP) // 2
    card_h = STEAM_CARD_H
    if steam:
        for index, deal in enumerate(steam[:12]):
            col = index % 2
            row = index // 2
            x = PADDING + col * (card_w + GAP)
            draw_steam_card(image, draw, session, deal, x, y + row * (card_h + GAP), card_w, card_h)
        y += steam_rows * (card_h + GAP)
    else:
        rounded_rect(draw, (PADDING, y, WIDTH - PADDING, y + 90), fill=PANEL, outline=LINE, radius=12)
        draw.text((PADDING + 20, y + 30), "暂时没有抓到 Steam 折扣榜，稍后再试。", fill=MUTED, font=FONT_CARD_TEXT)
        y += 110

    y += 22
    y = draw_section_title(draw, y, "Epic 喜加一", "包含当前免费与已公布的即将免费游戏")

    epic_cards = [(item, True) for item in epic_current[:2]] + [(item, False) for item in epic_upcoming[:2]]
    epic_card_h = EPIC_CARD_H
    if epic_cards:
        for index, (item, current) in enumerate(epic_cards[:4]):
            col = index % 2
            row = index // 2
            x = PADDING + col * (card_w + GAP)
            draw_epic_card(image, draw, session, item, x, y + row * (epic_card_h + GAP), card_w, epic_card_h, current)
        y += epic_rows * (epic_card_h + GAP)
    else:
        rounded_rect(draw, (PADDING, y, WIDTH - PADDING, y + 90), fill=PANEL_2, outline=LINE, radius=12)
        draw.text((PADDING + 20, y + 30), "暂时没有抓到 Epic 免费游戏，稍后再试。", fill=MUTED, font=FONT_CARD_TEXT)
        y += 110

    errors = data.get("errors") if isinstance(data.get("errors"), list) else []
    footer = "数据来源：Steam Store / Epic Games Store"
    if errors:
        footer += f" · 部分来源失败 {len(errors)} 项"
    draw.text((PADDING, height - 42), footer, fill=MUTED, font=FONT_SMALL)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=88, optimize=True)
    return output_path


def build_game_deals_update(steam_limit: int = 12, epic_country: str = "CN") -> tuple[str, Path, dict[str, Any]]:
    data = fetch_game_deals(steam_limit=steam_limit, epic_country=epic_country)
    image_path = render_game_deals_image(data)
    steam_count = len(data.get("steam") or [])
    epic = data.get("epic") if isinstance(data.get("epic"), dict) else {}
    current_count = len(epic.get("current") or [])
    upcoming_count = len(epic.get("upcoming") or [])
    caption = f"每日游戏优惠情报\nSteam 折扣榜 {steam_count} 个 · Epic 当前免费 {current_count} 个 / 即将免费 {upcoming_count} 个"
    return caption, image_path, data


def main() -> int:
    caption, image_path, data = build_game_deals_update()
    print(caption)
    print(f"Image: {image_path}")
    if data.get("errors"):
        print("Errors:")
        for error in data["errors"]:
            print(f"- {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
