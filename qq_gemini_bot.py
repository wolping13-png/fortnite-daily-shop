from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from send_qq_shop import build_message, choose_send_image, make_safe_image, post_onebot, should_prefer_section_pages


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"
SHOP_IMAGE_PATH = BASE_DIR / "shop_qq.jpg"
SHOP_JSON_PATH = BASE_DIR / "shop.json"
SHOP_SECTIONS_DIR = BASE_DIR / "shop_sections"
SHOP_SECTIONS_MANIFEST = SHOP_SECTIONS_DIR / "manifest.json"
WEATHER_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
WEEKDAYS_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

WEB_SEARCH_EXPLICIT_PREFIXES = (
    "联网查",
    "联网搜索",
    "联网搜",
    "搜索",
    "搜一下",
    "搜下",
    "查一下",
    "查查",
    "帮我搜",
    "帮我查",
)

WEB_SEARCH_AUTO_KEYWORDS = (
    "最新",
    "热点",
    "热搜",
    "新闻",
    "实时",
    "刚刚",
    "最近",
    "近期",
    "现在的",
    "资料",
)

WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    56: "冻毛毛雨",
    57: "较强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "较强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "gemini_bot_config.json not found. Copy gemini_bot_config.example.json first."
        )

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("gemini_bot_config.json must contain a JSON object.")

    provider = str(data.get("provider") or "gemini").lower()
    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY") or str(data.get("deepseek_api_key") or "")
        if not api_key or api_key == "PASTE_YOUR_DEEPSEEK_API_KEY_HERE":
            raise ValueError("DeepSeek API key is missing.")
        data["deepseek_api_key"] = api_key
    else:
        api_key = os.environ.get("GEMINI_API_KEY") or str(data.get("gemini_api_key") or "")
        if not api_key or api_key == "PASTE_YOUR_GEMINI_API_KEY_HERE":
            raise ValueError("Gemini API key is missing.")
        data["gemini_api_key"] = api_key

    tavily_api_key = os.environ.get("TAVILY_API_KEY") or str(data.get("tavily_api_key") or "")
    if tavily_api_key and tavily_api_key != "PASTE_YOUR_TAVILY_API_KEY_HERE":
        data["tavily_api_key"] = tavily_api_key
    else:
        data["tavily_api_key"] = ""

    return data


def normalize_base_url(value: str) -> str:
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value.rstrip("/") + "/"


def allowed_groups(config: dict[str, Any]) -> set[str]:
    return {str(group_id).strip() for group_id in config.get("allowed_group_ids", []) if str(group_id).strip()}


def config_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def extract_text(event: dict[str, Any]) -> str:
    raw = event.get("raw_message")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    message = event.get("message")
    if isinstance(message, str):
        return message.strip()

    if not isinstance(message, list):
        return ""

    parts: list[str] = []
    for segment in message:
        if not isinstance(segment, dict):
            continue
        if segment.get("type") != "text":
            continue
        data = segment.get("data")
        if isinstance(data, dict):
            parts.append(str(data.get("text") or ""))

    return "".join(parts).strip()


def bot_qq_ids(config: dict[str, Any], event: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for value in (
        event.get("self_id"),
        config.get("bot_qq"),
        config.get("bot_id"),
        config.get("self_id"),
    ):
        text = str(value or "").strip()
        if text and text.lower() not in {"none", "null", "0"}:
            ids.add(text)
    return ids


def extract_text_and_mention(event: dict[str, Any], config: dict[str, Any]) -> tuple[str, bool]:
    ids = bot_qq_ids(config, event)
    message = event.get("message")

    if isinstance(message, list):
        mentioned = False
        parts: list[str] = []
        for segment in message:
            if not isinstance(segment, dict):
                continue

            data = segment.get("data")
            if not isinstance(data, dict):
                data = {}

            if segment.get("type") == "at":
                qq = str(data.get("qq") or "").strip()
                if qq in ids:
                    mentioned = True
                continue

            if segment.get("type") == "text":
                parts.append(str(data.get("text") or ""))

        return "".join(parts).strip(), mentioned

    text = extract_text(event)
    mentioned = False

    def remove_at(match: re.Match[str]) -> str:
        nonlocal mentioned
        qq = str(match.group(1) or "").strip()
        if qq in ids:
            mentioned = True
            return " "
        return match.group(0)

    text = re.sub(r"\[CQ:at,qq=([0-9]+)\]", remove_at, text).strip()
    return text, mentioned


def send_group_text(config: dict[str, Any], group_id: int | str, text: str) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={
            "group_id": group_id,
            "message": [{"type": "text", "data": {"text": text}}],
        },
        access_token=access_token,
        timeout=60,
    )


def regenerate_shop_assets(include_sections: bool = False) -> None:
    commands = [
        [sys.executable, str(BASE_DIR / "update_shop.py")],
        [sys.executable, str(BASE_DIR / "generate_shop_image.py")],
    ]
    if include_sections:
        commands.append([sys.executable, str(BASE_DIR / "generate_shop_sections.py")])

    for command in commands:
        subprocess.run(command, cwd=BASE_DIR, check=True, timeout=180)


def ensure_shop_assets(include_sections: bool = False) -> None:
    needs_image = not SHOP_IMAGE_PATH.exists() and not (BASE_DIR / "shop.png").exists()
    needs_sections = include_sections and not SHOP_SECTIONS_MANIFEST.exists()
    if needs_image or needs_sections:
        regenerate_shop_assets(include_sections=include_sections)


def load_shop_pages(limit: int | None = None) -> list[tuple[Path, str]]:
    if not SHOP_SECTIONS_MANIFEST.exists():
        return []

    try:
        data = json.loads(SHOP_SECTIONS_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return []

    pages = data.get("pages")
    if not isinstance(pages, list):
        return []

    result: list[tuple[Path, str]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        path = BASE_DIR / str(page.get("path") or "")
        if not path.exists():
            continue
        caption = str(page.get("caption") or "Fortnite 每日商店")
        result.append((path, caption))
        if limit is not None and len(result) >= limit:
            break
    return result


def send_shop_image(config: dict[str, Any], group_id: int | str, send_all: bool = False) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    caption = str(config.get("shop_caption") or "Fortnite 每日商店")
    ensure_shop_assets(include_sections=send_all)
    if not send_all:
        image_path = SHOP_IMAGE_PATH if SHOP_IMAGE_PATH.exists() else BASE_DIR / "shop.png"
        if should_prefer_section_pages(image_path):
            ensure_shop_assets(include_sections=True)
            pages = load_shop_pages()
            if pages:
                try:
                    send_group_text(config, group_id, "商店总图太长，我直接发分区小图。")
                except Exception as exc:
                    print(f"Shop section notice failed: {exc}", file=sys.stderr)

                for page_path, page_caption in pages:
                    try:
                        post_onebot(
                            base_url=base_url,
                            action="send_group_msg",
                            payload={
                                "group_id": group_id,
                                "message": build_message(
                                    caption=f"{caption}\n{page_caption}",
                                    image_path=choose_send_image(page_path),
                                ),
                            },
                            access_token=access_token,
                            timeout=90,
                        )
                    except Exception as exc:
                        print(f"Shop section send failed for {page_path.name}: {exc}", file=sys.stderr)
                    time.sleep(0.6)
                return

        send_path = choose_send_image(image_path)
        message = build_message(caption=f"{caption}\n官方分区总图", image_path=send_path)
        result = post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={"group_id": group_id, "message": message},
            access_token=access_token,
            timeout=120,
        )
        if result.get("_napcat_callback_timeout"):
            safe_path = make_safe_image(image_path)
            retry = post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={
                    "group_id": group_id,
                    "message": build_message(
                        caption=f"{caption}\n原图回执超时，已改发压缩版。",
                        image_path=safe_path,
                    ),
                },
                access_token=access_token,
                timeout=120,
            )
            if retry.get("_napcat_callback_timeout"):
                ensure_shop_assets(include_sections=True)
                pages = load_shop_pages()
                if pages:
                    try:
                        send_group_text(config, group_id, "总图被 QQ 回执卡住了，我自动改发分区小图。")
                    except Exception as exc:
                        print(f"Shop fallback notice failed: {exc}", file=sys.stderr)

                    for page_path, page_caption in pages:
                        try:
                            post_onebot(
                                base_url=base_url,
                                action="send_group_msg",
                                payload={
                                    "group_id": group_id,
                                    "message": build_message(
                                        caption=f"{caption}\n{page_caption}",
                                        image_path=choose_send_image(page_path),
                                    ),
                                },
                                access_token=access_token,
                                timeout=90,
                            )
                        except Exception as exc:
                            print(f"Shop section fallback failed for {page_path.name}: {exc}", file=sys.stderr)
                        time.sleep(0.6)
                    return

                try:
                    send_group_text(
                        config,
                        group_id,
                        "商店图片发送被 QQ 回执卡住了。你可以发“商店全部”看分页版；如果 QQ 刚好抽风，稍后再试一下。",
                    )
                except Exception as exc:
                    print(f"Shop timeout notice failed: {exc}", file=sys.stderr)
        return

    pages = load_shop_pages()

    if pages:
        for index, (image_path, page_caption) in enumerate(pages, 1):
            text = f"{caption}\n{page_caption}"
            message = build_message(caption=text, image_path=image_path)
            post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={"group_id": group_id, "message": message},
                access_token=access_token,
                timeout=90,
            )
        return

    image_path = SHOP_IMAGE_PATH if SHOP_IMAGE_PATH.exists() else BASE_DIR / "shop.png"
    message = build_message(caption=f"{caption}\n官方分区总图", image_path=image_path)
    result = post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": message},
        access_token=access_token,
        timeout=90,
    )
    if result.get("_napcat_callback_timeout"):
        safe_path = make_safe_image(image_path)
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={
                "group_id": group_id,
                "message": build_message(
                    caption=f"{caption}\n原图回执超时，已改发压缩版。",
                    image_path=safe_path,
                ),
            },
            access_token=access_token,
            timeout=120,
        )


def send_reddit_pet_update(config: dict[str, Any], group_id: int | str, topic: str = "") -> None:
    from reddit_pets import build_reddit_pet_update

    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    limit = int(config.get("reddit_pet_limit") or 5)
    caption, image_path, posts = build_reddit_pet_update(limit=max(1, min(limit, 8)), topic=topic)
    if not posts:
        send_group_text(
            config,
            group_id,
            "暂时没抓到合适的 Reddit 宠物热点。可能是服务器访问 Reddit 被限流/拦截了；我已经把原因写到 logs/reddit_pets_debug.log。",
        )
        return

    message = build_message(caption=caption, image_path=image_path)
    post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": message},
        access_token=access_token,
        timeout=120,
    )


def send_x_posts_update(config: dict[str, Any], group_id: int | str, topic: str = "") -> None:
    from x_posts import build_x_posts_update

    bearer_token = str(config.get("x_bearer_token") or "")
    if not bearer_token:
        raise ValueError("X Bearer Token has not been configured.")

    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    limit = int(config.get("x_search_limit") or 3)
    fetch_limit = int(config.get("x_search_fetch_limit") or 10)
    fallback_query = str(
        config.get("x_search_query")
        or "(cat OR dog OR wolf OR fox OR 宠物 OR 猫 OR 狗 OR 狼 OR 狐狸) has:media -is:retweet"
    )

    caption, image_path, posts = build_x_posts_update(
        bearer_token=bearer_token,
        topic=topic,
        limit=max(1, min(limit, 5)),
        fetch_limit=max(10, min(fetch_limit, 100)),
        fallback_query=fallback_query,
    )
    if not posts:
        send_group_text(config, group_id, "暂时没抓到合适的 X 图片帖子。可能是 X API 没额度、搜索条件太窄，或者稍后再试。")
        return

    result = post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": build_message(caption=caption, image_path=choose_send_image(image_path))},
        access_token=access_token,
        timeout=120,
    )
    if result.get("_napcat_callback_timeout"):
        safe_path = make_safe_image(image_path)
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={
                "group_id": group_id,
                "message": build_message(caption=f"{caption}\n原图回执超时，已改发压缩版。", image_path=safe_path),
            },
            access_token=access_token,
            timeout=120,
        )


def send_game_deals_update(config: dict[str, Any], group_id: int | str) -> None:
    from game_deals import build_game_deals_update

    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    steam_limit = int(config.get("game_deals_steam_limit") or 12)
    epic_country = str(config.get("game_deals_epic_country") or "CN")
    caption, image_path, _data = build_game_deals_update(
        steam_limit=max(4, min(steam_limit, 20)),
        epic_country=epic_country,
    )
    result = post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": build_message(caption=caption, image_path=image_path)},
        access_token=access_token,
        timeout=120,
    )
    if result.get("_napcat_callback_timeout"):
        safe_path = make_safe_image(image_path)
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={
                "group_id": group_id,
                "message": build_message(caption=f"{caption}\n原图回执超时，已改发压缩版。", image_path=safe_path),
            },
            access_token=access_token,
            timeout=120,
        )


def send_random_food_update(config: dict[str, Any], group_id: int | str, kind: str) -> None:
    from random_food import build_random_food_recommendation

    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    tavily_api_key = str(config.get("tavily_api_key") or "")
    caption, image_path, _item = build_random_food_recommendation(kind, tavily_api_key=tavily_api_key)
    result = post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": build_message(caption=caption, image_path=image_path)},
        access_token=access_token,
        timeout=120,
    )
    if result.get("_napcat_callback_timeout"):
        safe_path = make_safe_image(image_path)
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={
                "group_id": group_id,
                "message": build_message(caption=f"{caption}\n原图回执超时，已改发压缩版。", image_path=safe_path),
            },
            access_token=access_token,
            timeout=120,
        )


def send_random_wolf_update(config: dict[str, Any], group_id: int | str, caption: str = "狼狼来啦") -> None:
    from random_wolf import build_random_wolf

    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")
    tavily_api_key = str(config.get("tavily_api_key") or "")
    generated_caption, image_path, _item = build_random_wolf(tavily_api_key=tavily_api_key)
    text = caption or generated_caption
    result = post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": build_message(caption=text, image_path=image_path)},
        access_token=access_token,
        timeout=120,
    )
    if result.get("_napcat_callback_timeout"):
        safe_path = make_safe_image(image_path)
        post_onebot(
            base_url=base_url,
            action="send_group_msg",
            payload={
                "group_id": group_id,
                "message": build_message(caption=f"{text}\n原图回执超时，已改发压缩版。", image_path=safe_path),
            },
            access_token=access_token,
            timeout=120,
        )


def is_pet_hot_request(text: str, configured_command: str) -> bool:
    value = re.sub(r"\s+", "", text.strip().lower())
    command = re.sub(r"\s+", "", configured_command.strip().lower())
    return bool(command) and value == command


def random_food_kind(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text.strip().lower())
    food_triggers = {
        "吃什么",
        "今天吃什么",
        "中午吃什么",
        "午饭吃什么",
        "晚上吃什么",
        "晚饭吃什么",
        "夜宵吃什么",
        "吃点什么",
        "整点吃的",
    }
    drink_triggers = {
        "喝什么",
        "今天喝什么",
        "喝点什么",
        "整点喝的",
        "饮料喝什么",
        "奶茶喝什么",
        "咖啡喝什么",
    }
    if compact in food_triggers:
        return "food"
    if compact in drink_triggers:
        return "drink"
    return None


def is_wolf_request(text: str, configured_command: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip().lower())
    command = re.sub(r"\s+", "", configured_command.strip().lower())
    return compact == (command or "狼狼")


def is_x_posts_request(text: str, configured_command: str) -> bool:
    value = text.strip().lower()
    compact = re.sub(r"\s+", "", value)
    commands = {
        configured_command.strip().lower(),
        "x宠物",
        "x热点",
        "x帖子",
        "x狼狼",
        "x福瑞",
        "xfurry",
        "x兽设",
        "x兽人",
        "推特宠物",
        "推特热点",
        "推特帖子",
        "推特狼狼",
        "推特福瑞",
        "推特兽设",
        "twitter宠物",
        "twitter热点",
        "twitter帖子",
        "twitter狼狼",
        "twitterfurry",
    }
    compact_commands = {re.sub(r"\s+", "", command) for command in commands if command}
    if compact in compact_commands:
        return True
    return compact.startswith(("x搜", "x找", "x看", "推特搜", "推特找", "twitter搜"))


def is_help_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip().lower())
    return compact in {"指令", "帮助", "菜单", "使用说明", "功能", "help", "commands"}


def command_help_text(config: dict[str, Any]) -> str:
    ask_prefix = str(config.get("ask_prefix") or "温德尔")
    shop_command = str(config.get("shop_command") or "商店")
    shop_all_command = str(config.get("shop_all_command") or "商店全部")
    weather_command = str(config.get("weather_command") or "天气")
    web_search_command = str(config.get("web_search_command") or "联网查")
    game_deals_command = str(config.get("game_deals_command") or "游戏优惠")
    wolf_command = str(config.get("wolf_command") or "狼狼")
    x_search_command = str(config.get("x_search_command") or "X宠物")

    return (
        "温德尔指令表\n"
        "\n"
        "直接发：\n"
        f"- {shop_command}：发送 Fortnite 每日商店总图\n"
        f"- {shop_all_command}：发送 Fortnite 商店分区图\n"
        f"- {game_deals_command} / Steam折扣榜 / Epic喜加一：发送游戏优惠日报\n"
        "- 吃什么：随机推荐食物并发实物图\n"
        "- 喝什么：随机推荐饮品并发实物图\n"
        f"- {weather_command} 北京 / 今天武汉洪山区天气怎么样：查天气\n"
        "\n"
        "需要艾特我：\n"
        "- @我 指令：显示这份指令表\n"
        f"- @我 {wolf_command}：随机发一张狼图\n"
        f"- @我 {x_search_command} / X狼狼 / X福瑞：抓取 X 公开图片帖子并生成卡片\n"
        f"- @我 {web_search_command} 最近有什么游戏新闻：联网搜索，文字和图片尽量合在一条消息里\n"
        "- @我 今天几号 / 推荐几个游戏 / 你想问的问题：普通聊天\n"
        f"- {ask_prefix} 你的问题：旧版前缀聊天，也还能用"
    )


def is_game_deals_request(text: str, configured_command: str) -> bool:
    value = text.strip().lower()
    compact = re.sub(r"\s+", "", value)
    commands = {
        configured_command.strip().lower(),
        "游戏优惠",
        "游戏折扣",
        "折扣榜",
        "steam折扣",
        "steam折扣榜",
        "steam优惠",
        "epic喜加一",
        "epic免费",
        "喜加一",
    }
    if compact in {re.sub(r"\s+", "", command) for command in commands if command}:
        return True
    return (
        ("steam" in compact and ("折扣" in compact or "优惠" in compact or "销量" in compact))
        or ("epic" in compact and ("喜加一" in compact or "免费" in compact))
        or ("游戏" in compact and ("折扣" in compact or "优惠" in compact))
    )


def split_reply(text: str, limit: int = 900) -> list[str]:
    value = text.strip()
    if len(value) <= limit:
        return [value]

    chunks: list[str] = []
    while value:
        chunk = value[:limit]
        cut = max(chunk.rfind("\n"), chunk.rfind("。"), chunk.rfind("！"), chunk.rfind("？"))
        if cut > 200:
            chunk = value[: cut + 1]
        chunks.append(chunk.strip())
        value = value[len(chunk) :].strip()
    return chunks


def weather_text(code: Any) -> str:
    try:
        return WEATHER_CODES.get(int(code), "未知天气")
    except Exception:
        return "未知天气"


def is_weather_question(text: str) -> bool:
    value = text.strip()
    if not any(keyword in value for keyword in ("天气", "气温", "温度", "下雨", "降雨", "预报")):
        return False
    return any(
        keyword in value
        for keyword in (
            "今天",
            "明天",
            "后天",
            "现在",
            "当前",
            "怎么样",
            "如何",
            "多少",
            "会不会",
            "查",
            "看",
            "吗",
            "呢",
            "?",
            "？",
        )
    )


def weather_location_candidates(location: str) -> list[str]:
    value = location.strip()
    candidates: list[str] = []

    def add(candidate: str) -> None:
        candidate = candidate.strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(value)

    compact = re.sub(r"\s+", "", value)
    add(compact)

    if compact.endswith(("区", "县", "旗")) and len(compact) > 2:
        add(compact[:-1])

    city_match = re.match(r"(.+?市)", compact)
    if city_match:
        add(city_match.group(1))
        add(city_match.group(1).removesuffix("市"))

    known_cities = (
        "北京",
        "上海",
        "天津",
        "重庆",
        "武汉",
        "广州",
        "深圳",
        "杭州",
        "南京",
        "成都",
        "西安",
        "长沙",
        "郑州",
        "苏州",
        "青岛",
        "厦门",
        "福州",
        "济南",
        "沈阳",
        "大连",
        "哈尔滨",
        "长春",
        "昆明",
        "贵阳",
        "南宁",
        "海口",
        "石家庄",
        "太原",
        "合肥",
        "南昌",
        "兰州",
        "银川",
        "西宁",
        "乌鲁木齐",
        "拉萨",
        "香港",
        "澳门",
        "台北",
    )
    for city in known_cities:
        if city in compact:
            add(city)

    return candidates


def extract_weather_location(question: str, default_location: str = "") -> tuple[str, int]:
    value = question.strip()
    day_index = 0
    if "后天" in value:
        day_index = 2
    elif "明天" in value or "明日" in value:
        day_index = 1

    for token in (
        "天气",
        "气温",
        "温度",
        "预报",
        "下雨",
        "降雨",
        "今天",
        "现在",
        "当前",
        "实时",
        "明天",
        "明日",
        "后天",
        "帮我",
        "查一下",
        "查下",
        "查询",
        "看看",
        "看下",
        "怎么样",
        "如何",
        "会不会",
        "吗",
        "呢",
        "呀",
        "的",
    ):
        value = value.replace(token, " ")

    value = re.sub(r"[，。！？、：:,.!?；;（）()\[\]【】]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or default_location.strip(), day_index


def first_value(values: list[Any], index: int, default: Any = None) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return default
    return values[index]


def format_number(value: Any, suffix: str = "") -> str:
    if isinstance(value, (int, float)):
        rounded = round(float(value), 1)
        text = str(int(rounded)) if rounded.is_integer() else str(rounded)
        return f"{text}{suffix}"
    return f"未知{suffix}" if suffix else "未知"


def ask_weather(config: dict[str, Any], question: str) -> str:
    default_location = str(config.get("default_weather_location") or "")
    location, day_index = extract_weather_location(question, default_location)
    if not location:
        return "你想查哪里的天气？比如：温德尔 北京天气"

    place = None
    used_location = location
    for candidate in weather_location_candidates(location):
        geo_response = requests.get(
            WEATHER_GEOCODING_URL,
            params={"name": candidate, "count": 1, "language": "zh", "format": "json"},
            timeout=20,
        )
        geo_response.raise_for_status()
        geo_data = geo_response.json()
        results = geo_data.get("results")
        if isinstance(results, list) and results:
            place = results[0]
            used_location = candidate
            break

    if not isinstance(place, dict):
        return f"我没找到“{location}”这个地方的天气。可以换成城市名试试，比如：北京天气。"

    latitude = place.get("latitude")
    longitude = place.get("longitude")
    if latitude is None or longitude is None:
        return f"我找到了“{location}”，但没有拿到经纬度，暂时查不了天气。"

    forecast_response = requests.get(
        WEATHER_FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "precipitation_sum",
                ]
            ),
            "timezone": "auto",
            "forecast_days": 3,
        },
        timeout=20,
    )
    forecast_response.raise_for_status()
    weather = forecast_response.json()

    current = weather.get("current") if isinstance(weather.get("current"), dict) else {}
    daily = weather.get("daily") if isinstance(weather.get("daily"), dict) else {}
    day_label = ["今天", "明天", "后天"][min(day_index, 2)]

    name = str(place.get("name") or location)
    admin = str(place.get("admin1") or "")
    country = str(place.get("country") or "")
    place_name = " ".join(part for part in (country, admin, name) if part)

    day_weather_code = first_value(daily.get("weather_code"), day_index)
    min_temp = first_value(daily.get("temperature_2m_min"), day_index)
    max_temp = first_value(daily.get("temperature_2m_max"), day_index)
    rain_probability = first_value(daily.get("precipitation_probability_max"), day_index)
    rain_sum = first_value(daily.get("precipitation_sum"), day_index)

    lines = [
        f"{place_name}天气：",
        f"现在：{weather_text(current.get('weather_code'))}，{format_number(current.get('temperature_2m'), '°C')}，体感 {format_number(current.get('apparent_temperature'), '°C')}，湿度 {format_number(current.get('relative_humidity_2m'), '%')}",
        f"风速：{format_number(current.get('wind_speed_10m'), ' km/h')}，当前降水 {format_number(current.get('precipitation'), ' mm')}",
        f"{day_label}：{weather_text(day_weather_code)}，{format_number(min_temp, '°C')} ~ {format_number(max_temp, '°C')}，降水概率最高 {format_number(rain_probability, '%')}，预计降水 {format_number(rain_sum, ' mm')}",
        "数据来自 Open-Meteo，天气会有误差，出门前最好再看一下本地天气 App。",
    ]
    if used_location != location:
        lines.insert(1, f"我没有精确匹配到“{location}”，先按“{used_location}”附近查询。")
    return "\n".join(lines)


def is_shop_question(question: str) -> bool:
    value = question.lower()
    keywords = (
        "商店",
        "商城",
        "皮肤",
        "价格",
        "v-buck",
        "vbuck",
        "vbucks",
        "fortnite",
        "堡垒",
        "今天有什么",
        "推荐",
    )
    return any(keyword in value for keyword in keywords)


def load_shop_summary(max_items: int = 120) -> str:
    if not SHOP_JSON_PATH.exists():
        return "今天的 Fortnite 商店数据文件还没有生成。"

    try:
        data = json.loads(SHOP_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "今天的 Fortnite 商店数据文件读取失败。"

    items = data.get("items")
    if not isinstance(items, list) or not items:
        return "今天的 Fortnite 商店数据为空。"

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        section = str(item.get("section") or "未分区")
        groups.setdefault(section, []).append(item)

    lines = [
        "今天 Fortnite 每日商店真实数据如下。回答时只基于这些数据，不要编造普通电商商品、优惠券或现实世界商店内容。",
        f"更新时间：{data.get('updatedAt') or data.get('date') or '未知'}",
    ]

    count = 0
    for section, section_items in groups.items():
        lines.append(f"\n分区：{section}")
        for item in section_items:
            if count >= max_items:
                lines.append("还有更多商品，已省略。")
                return "\n".join(lines)

            name = str(item.get("name") or "未知物品")
            rarity = str(item.get("rarity") or "未知稀有度")
            price = item.get("price")
            price_text = f"{price} V-Bucks" if price is not None else "未知价格"
            lines.append(f"- {name} | {rarity} | {price_text}")
            count += 1

    return "\n".join(lines)


def enrich_question(question: str) -> str:
    if not is_shop_question(question):
        return question

    return (
        f"{question}\n\n"
        "请注意：用户说的“商店”默认指 Fortnite 每日商店，不是普通电商平台。\n"
        "请根据下面的数据，用简体中文总结亮点、分区、值得注意的联动/稀有度/价格。不要编造数据里没有的商品。\n\n"
        f"{load_shop_summary()}"
    )


def current_time_context() -> str:
    now = datetime.now(CHINA_TZ)
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)
    return (
        "当前时间信息：\n"
        f"- 中国内地北京时间现在是 {now:%Y-%m-%d %H:%M:%S}，{WEEKDAYS_ZH[now.weekday()]}。\n"
        f"- 今天 = {now:%Y-%m-%d}。\n"
        f"- 昨天 = {yesterday:%Y-%m-%d}。\n"
        f"- 明天 = {tomorrow:%Y-%m-%d}。\n"
        "- 回答任何日期、今天、昨天、明天、最近、最新、今晚、明早相关问题时，都必须以这段北京时间为准。"
    )


def add_time_context_to_prompt(question: str) -> str:
    return f"{current_time_context()}\n\n用户问题：{question}"


def add_time_context_to_system(system_prompt: str) -> str:
    return (
        f"{system_prompt.rstrip()}\n\n"
        f"{current_time_context()}\n"
        "如果用户询问当前日期或相对日期，直接给出具体日期，不要猜。"
    )


def is_explicit_web_search_command(text: str, configured_command: str) -> bool:
    value = text.strip()
    prefixes = [configured_command.strip()] if configured_command.strip() else []
    prefixes.extend(WEB_SEARCH_EXPLICIT_PREFIXES)
    return any(value.startswith(prefix) for prefix in prefixes if prefix)


def should_use_web_search(question: str, configured_command: str) -> bool:
    value = question.strip()
    if not value:
        return False
    if is_explicit_web_search_command(value, configured_command):
        return True
    return any(keyword in value for keyword in WEB_SEARCH_AUTO_KEYWORDS)


def strip_web_search_command(question: str, configured_command: str) -> str:
    value = question.strip()
    prefixes = [configured_command.strip()] if configured_command.strip() else []
    prefixes.extend(WEB_SEARCH_EXPLICIT_PREFIXES)
    for prefix in prefixes:
        if prefix and value.startswith(prefix):
            return value[len(prefix) :].strip().lstrip("：:，, ")
    return value


def tavily_search(config: dict[str, Any], query: str) -> dict[str, Any]:
    api_key = str(config.get("tavily_api_key") or "").strip()
    if not api_key:
        raise ValueError("Tavily API key is missing.")

    max_results = int(config.get("web_search_max_results") or 5)
    max_results = max(1, min(max_results, 10))
    search_depth = str(config.get("web_search_depth") or "basic").lower()
    if search_depth not in {"basic", "advanced"}:
        search_depth = "basic"

    topic = str(config.get("web_search_topic") or "").strip().lower()
    if not topic:
        topic = "news" if any(word in query for word in ("新闻", "热点", "热搜", "最新")) else "general"
    if topic not in {"general", "news"}:
        topic = "general"

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "topic": topic,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": bool(config.get("web_search_include_answer", False)),
            "include_raw_content": False,
            "include_images": bool(config.get("web_search_include_images", True)),
        },
        timeout=40,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Tavily returned an unexpected response.")
    return data


def format_web_search_context(data: dict[str, Any]) -> str:
    lines: list[str] = []
    answer = str(data.get("answer") or "").strip()
    if answer:
        lines.append(f"Tavily answer: {answer}")

    results = data.get("results")
    if not isinstance(results, list) or not results:
        return "\n".join(lines) if lines else "没有搜索结果。"

    for index, item in enumerate(results[:8], 1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "无标题").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        published_date = str(item.get("published_date") or "").strip()
        score = item.get("score")
        meta = []
        if published_date:
            meta.append(f"date={published_date}")
        if isinstance(score, (int, float)):
            meta.append(f"score={score:.3f}")
        meta_text = f" ({', '.join(meta)})" if meta else ""
        lines.append(f"[{index}] {title}{meta_text}\nURL: {url}\n摘要: {content}")

    return "\n\n".join(lines)


def web_search_image_urls(data: dict[str, Any], limit: int = 2) -> list[str]:
    urls: list[str] = []

    def add_url(value: Any) -> None:
        if isinstance(value, str):
            url = value.strip()
        elif isinstance(value, dict):
            url = str(value.get("url") or "").strip()
        else:
            return

        lower = url.lower()
        if not url or url in urls:
            return
        if lower.endswith((".svg", ".gif", ".webm", ".mp4")):
            return
        urls.append(url)

    images = data.get("images")
    if isinstance(images, list):
        for image in images:
            add_url(image)

    results = data.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict):
                continue
            result_images = result.get("images")
            if isinstance(result_images, list):
                for image in result_images:
                    add_url(image)

    return urls[: max(0, limit)]


def send_web_search_reply(config: dict[str, Any], group_id: int | str, answer: str, image_urls: list[str]) -> None:
    base_url = normalize_base_url(str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    access_token = str(config.get("access_token") or "")

    if image_urls:
        message: list[dict[str, Any]] = []
        if answer.strip():
            message.append({"type": "text", "data": {"text": answer.strip() + "\n"}})
        for image_url in image_urls:
            message.append({"type": "image", "data": {"file": image_url}})

        try:
            post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={"group_id": group_id, "message": message},
                access_token=access_token,
                timeout=120,
            )
            return
        except Exception as exc:
            print(f"Web search rich message send failed: {exc}", file=sys.stderr)

    for chunk in split_reply(answer):
        send_group_text(config, group_id, chunk)

    for index, image_url in enumerate(image_urls, 1):
        try:
            post_onebot(
                base_url=base_url,
                action="send_group_msg",
                payload={
                    "group_id": group_id,
                    "message": build_message(
                        caption=f"相关图片 {index}",
                        image_path=BASE_DIR / "unused.jpg",
                        image_url=image_url,
                    ),
                },
                access_token=access_token,
                timeout=120,
            )
        except Exception as exc:
            print(f"Web search image send failed: {image_url} {exc}", file=sys.stderr)


def ask_model_with_web_search(config: dict[str, Any], question: str) -> tuple[str, list[str]]:
    search_query = strip_web_search_command(question, str(config.get("web_search_command") or "联网查"))
    if not search_query:
        search_query = question

    search_data = tavily_search(config, search_query)
    image_limit = int(config.get("web_search_image_limit") or 2)
    image_urls = web_search_image_urls(search_data, limit=max(0, min(image_limit, 4)))
    context = format_web_search_context(search_data)
    prompt = (
        f"{current_time_context()}\n\n"
        f"用户问题：{search_query}\n\n"
        "下面是 Tavily 联网搜索结果。请只基于这些结果和你已有的通用知识回答；"
        "如果搜索结果不足或互相矛盾，要直接说明不确定。用简体中文，语气自然，尽量简洁。"
        "涉及今天、昨天、明天、最近、最新、今晚、明早时，必须结合上面的北京时间判断。"
        "最后用“参考：”列出最多 3 个来源标题或链接。\n\n"
        f"{context}"
    )
    return ask_model(config, prompt), image_urls


def ask_gemini(config: dict[str, Any], question: str) -> str:
    model = str(config.get("model") or "gemini-2.0-flash")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    system_prompt = str(
        config.get("system_prompt")
        or "你叫温德尔，是一个友好的 QQ 群游戏助手。你是游戏专家，尤其熟悉 Fortnite / 堡垒之夜，但也可以聊其他游戏、攻略、更新、电竞、硬件配置、主机、PC 和手游。用户说“商店”时，默认指 Fortnite 每日商店。回答用简体中文，像朋友聊天一样自然、有趣、实用；不确定就直接说不确定，不要编造。"
    )
    system_prompt = add_time_context_to_system(system_prompt)

    user_question = add_time_context_to_prompt(enrich_question(question))

    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": str(config["gemini_api_key"]),
        },
        json={
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_question}],
                }
            ],
            "generationConfig": {
                "temperature": float(config.get("temperature", 0.7)),
                "maxOutputTokens": int(config.get("max_output_tokens", 700)),
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return "Gemini 没有返回内容。"

    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [str(part.get("text") or "") for part in parts if isinstance(part, dict)]
    answer = "\n".join(text for text in texts if text.strip()).strip()
    return answer or "Gemini 没有返回文字内容。"


def ask_deepseek(config: dict[str, Any], question: str) -> str:
    base_url = str(config.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/")
    model = str(config.get("model") or "deepseek-v4-flash")
    system_prompt = str(
        config.get("system_prompt")
        or "你叫温德尔，是一个友好的 QQ 群游戏助手。你是游戏专家，尤其熟悉 Fortnite / 堡垒之夜，但也可以聊其他游戏、攻略、更新、电竞、硬件配置、主机、PC 和手游。用户说“商店”时，默认指 Fortnite 每日商店。回答用简体中文，像朋友聊天一样自然、有趣、实用；不确定就直接说不确定，不要编造。"
    )
    system_prompt = add_time_context_to_system(system_prompt)

    user_question = add_time_context_to_prompt(enrich_question(question))

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['deepseek_api_key']}",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ],
            "temperature": float(config.get("temperature", 0.7)),
            "max_tokens": int(config.get("max_output_tokens", 700)),
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return "DeepSeek 没有返回内容。"

    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return "DeepSeek 没有返回文字内容。"
    answer = str(message.get("content") or "").strip()
    return answer or "DeepSeek 没有返回文字内容。"


def ask_model(config: dict[str, Any], question: str) -> str:
    provider = str(config.get("provider") or "gemini").lower()
    if provider == "deepseek":
        return ask_deepseek(config, question)
    return ask_gemini(config, question)


def handle_event(config: dict[str, Any], event: dict[str, Any]) -> None:
    if event.get("post_type") != "message":
        return
    if event.get("message_type") != "group":
        return

    group_id = event.get("group_id")
    if group_id is None:
        return

    groups = allowed_groups(config)
    if groups and str(group_id) not in groups:
        return

    text, mentioned = extract_text_and_mention(event, config)
    if not text:
        if mentioned:
            send_group_text(config, group_id, "我在，直接问我就行。比如：@我 今天武汉天气怎么样")
        return

    ask_prefix = str(config.get("ask_prefix") or "温德尔")
    shop_command = str(config.get("shop_command") or "商店")
    shop_all_command = str(config.get("shop_all_command") or "商店全部")
    weather_command = str(config.get("weather_command") or "天气")
    pet_command = str(config.get("pet_command") or "宠物热点")
    reddit_pet_enabled = config_bool(config.get("reddit_pet_enabled"), False)
    web_search_command = str(config.get("web_search_command") or "联网查")
    game_deals_command = str(config.get("game_deals_command") or "游戏优惠")
    wolf_command = str(config.get("wolf_command") or "狼狼")

    if is_help_request(text):
        for chunk in split_reply(command_help_text(config), limit=850):
            send_group_text(config, group_id, chunk)
        return

    if text in {shop_command, shop_all_command}:
        try:
            send_shop_image(config, group_id, send_all=text == shop_all_command)
        except Exception as exc:
            print(f"Shop image send failed: {exc}", file=sys.stderr)
            send_group_text(config, group_id, "商店图片暂时发送失败了。我已经把错误写进后台日志，请稍后再试一下。")
        return

    if mentioned and is_wolf_request(text, wolf_command):
        try:
            send_random_wolf_update(config, group_id)
        except Exception as exc:
            print(f"Random wolf update failed: {exc}", file=sys.stderr)
            send_group_text(config, group_id, "狼狼图片暂时找不到能发送的真实照片，稍后再试一下。")
        return

    if is_x_posts_request(text, x_search_command):
        try:
            send_x_posts_update(config, group_id, topic=text)
        except ValueError:
            send_group_text(config, group_id, "X API 还没配置 Bearer Token。先把 x_bearer_token 填进 gemini_bot_config.json，然后重启我。")
        except Exception as exc:
            print(f"X posts update failed: {exc}", file=sys.stderr)
            send_group_text(config, group_id, "X 图片帖子暂时抓取失败。可能是 token 没权限、额度不足，或者 X API 暂时限制了请求。")
        return

    food_kind = random_food_kind(text)
    if food_kind:
        try:
            send_random_food_update(config, group_id, food_kind)
        except Exception as exc:
            print(f"Random food update failed: {exc}", file=sys.stderr)
            send_group_text(config, group_id, "随机推荐暂时找不到能发送的真实图片。请确认 tavily_api_key 已配置，或者稍后再试一下。")
        return

    if is_game_deals_request(text, game_deals_command):
        try:
            send_game_deals_update(config, group_id)
        except Exception as exc:
            print(f"Game deals update failed: {exc}", file=sys.stderr)
            send_group_text(config, group_id, "游戏优惠日报暂时抓取失败，稍后再试一下。")
        return

    if reddit_pet_enabled and is_pet_hot_request(text, pet_command):
        try:
            send_reddit_pet_update(config, group_id, topic=text)
        except Exception as exc:
            print(f"Reddit pet update failed: {exc}", file=sys.stderr)
            send_group_text(config, group_id, "Reddit 宠物热点暂时抓取失败，稍后再试一下。")
        return

    if is_explicit_web_search_command(text, web_search_command):
        try:
            answer, image_urls = ask_model_with_web_search(config, text)
        except ValueError as exc:
            print(f"Web search request failed: {exc}", file=sys.stderr)
            answer = "联网搜索还没配置 Tavily API Key。把 tavily_api_key 填进 gemini_bot_config.json 后重启我就能搜了。"
            image_urls = []
        except Exception as exc:
            print(f"Web search request failed: {exc}", file=sys.stderr)
            answer = "联网搜索暂时失败了，稍后再试一下。"
            image_urls = []
        send_web_search_reply(config, group_id, answer, image_urls)
        return

    if text.startswith(weather_command):
        weather_question = text[len(weather_command) :].strip()
        try:
            answer = ask_weather(config, weather_question)
        except Exception as exc:
            print(f"Weather request failed: {exc}", file=sys.stderr)
            answer = "天气暂时查不到，稍后再试一下。"
        send_group_text(config, group_id, answer)
        return

    if is_weather_question(text):
        try:
            answer = ask_weather(config, text)
        except Exception as exc:
            print(f"Weather request failed: {exc}", file=sys.stderr)
            answer = "天气暂时查不到，稍后再试一下。"
        send_group_text(config, group_id, answer)
        return

    if mentioned:
        question = text.strip().lstrip(" ：:，,")
    elif text.startswith(ask_prefix):
        question = text[len(ask_prefix) :].strip()
        question = question.lstrip(" ：:，,")
    else:
        return

    if not question:
        send_group_text(config, group_id, "用法：@我 你想问的问题")
        return

    if is_help_request(question):
        for chunk in split_reply(command_help_text(config), limit=850):
            send_group_text(config, group_id, chunk)
        return

    if is_weather_question(question):
        try:
            answer = ask_weather(config, question)
        except Exception as exc:
            print(f"Weather request failed: {exc}", file=sys.stderr)
            answer = "天气暂时查不到，稍后再试一下。"
        send_group_text(config, group_id, answer)
        return

    image_urls: list[str] = []
    try:
        if should_use_web_search(question, web_search_command):
            answer, image_urls = ask_model_with_web_search(config, question)
        else:
            answer = ask_model(config, question)
    except ValueError as exc:
        print(f"Model request failed: {exc}", file=sys.stderr)
        if "Tavily API key" in str(exc):
            send_group_text(config, group_id, "联网搜索还没配置 Tavily API Key。把 tavily_api_key 填进 gemini_bot_config.json 后重启我就能搜了。")
        else:
            send_group_text(config, group_id, "AI 暂时没有回复成功，稍后再试一下。")
        return
    except Exception as exc:
        print(f"Model request failed: {exc}", file=sys.stderr)
        send_group_text(config, group_id, "AI 暂时没有回复成功，稍后再试一下。")
        return

    send_web_search_reply(config, group_id, answer, image_urls)


class OneBotHandler(BaseHTTPRequestHandler):
    config: dict[str, Any] = {}

    def read_body(self) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" not in transfer_encoding:
            length = int(self.headers.get("Content-Length") or "0")
            return self.rfile.read(length)

        body = bytearray()
        while True:
            size_line = self.rfile.readline().strip()
            if not size_line:
                continue

            chunk_size = int(size_line.split(b";", 1)[0], 16)
            if chunk_size == 0:
                self.rfile.readline()
                break

            body.extend(self.rfile.read(chunk_size))
            self.rfile.readline()

        return bytes(body)

    def do_POST(self) -> None:
        try:
            body = self.read_body()
            if not body.strip():
                self.send_response(204)
                self.end_headers()
                return

            event = json.loads(body.decode("utf-8"))
            if isinstance(event, dict):
                threading.Thread(target=handle_event, args=(self.config, event), daemon=True).start()

            self.send_response(204)
            self.end_headers()
        except json.JSONDecodeError:
            self.send_response(204)
            self.end_headers()
        except Exception as exc:
            print(f"Failed to handle OneBot event: {exc}", file=sys.stderr)
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    config = load_config()
    host = str(config.get("listen_host") or "127.0.0.1")
    port = int(config.get("listen_port") or 8080)
    OneBotHandler.config = config

    server = ThreadingHTTPServer((host, port), OneBotHandler)
    print(f"Gemini QQ bot listening on http://{host}:{port}/onebot")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
