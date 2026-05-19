from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from game_deals import fetch_game_deals
from send_qq_shop import load_config, normalize_base_url, normalize_group_ids, post_onebot


try:
    from lunardate import LunarDate
except Exception:  # pragma: no cover - optional runtime dependency fallback
    LunarDate = None  # type: ignore[assignment]


BASE_DIR = Path(__file__).resolve().parent
QQ_CONFIG_PATH = BASE_DIR / "qq_bot_config.json"
BOT_CONFIG_PATH = BASE_DIR / "gemini_bot_config.json"
CHINA_TZ = ZoneInfo("Asia/Shanghai")

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
LUNAR_MONTHS = ["正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "冬月", "腊月"]
LUNAR_DAYS = [
    "初一",
    "初二",
    "初三",
    "初四",
    "初五",
    "初六",
    "初七",
    "初八",
    "初九",
    "初十",
    "十一",
    "十二",
    "十三",
    "十四",
    "十五",
    "十六",
    "十七",
    "十八",
    "十九",
    "二十",
    "廿一",
    "廿二",
    "廿三",
    "廿四",
    "廿五",
    "廿六",
    "廿七",
    "廿八",
    "廿九",
    "三十",
]

SOLAR_FESTIVALS = {
    (1, 1): ["元旦"],
    (2, 14): ["情人节"],
    (3, 8): ["妇女节"],
    (3, 12): ["植树节"],
    (4, 1): ["愚人节"],
    (5, 1): ["劳动节"],
    (5, 4): ["青年节"],
    (6, 1): ["儿童节"],
    (7, 1): ["建党节"],
    (8, 1): ["建军节"],
    (9, 10): ["教师节"],
    (10, 1): ["国庆节"],
    (12, 24): ["平安夜"],
    (12, 25): ["圣诞节"],
}

LUNAR_FESTIVALS = {
    (1, 1): ["春节"],
    (1, 15): ["元宵节"],
    (2, 2): ["龙抬头"],
    (5, 5): ["端午节"],
    (7, 7): ["七夕"],
    (7, 15): ["中元节"],
    (8, 15): ["中秋节"],
    (9, 9): ["重阳节"],
    (12, 8): ["腊八节"],
    (12, 23): ["小年"],
}


def load_bot_config() -> dict[str, Any]:
    if not BOT_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(BOT_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def lunar_info(day: date) -> tuple[str, list[str]]:
    if LunarDate is None:
        return "", []

    lunar = LunarDate.fromSolarDate(day.year, day.month, day.day)
    month_name = LUNAR_MONTHS[lunar.month - 1] if 1 <= lunar.month <= 12 else f"{lunar.month}月"
    day_name = LUNAR_DAYS[lunar.day - 1] if 1 <= lunar.day <= len(LUNAR_DAYS) else f"{lunar.day}日"
    prefix = "闰" if getattr(lunar, "isLeapMonth", False) else ""
    festivals = list(LUNAR_FESTIVALS.get((lunar.month, lunar.day), []))

    next_lunar = LunarDate.fromSolarDate(
        (day + timedelta(days=1)).year,
        (day + timedelta(days=1)).month,
        (day + timedelta(days=1)).day,
    )
    if lunar.month != 1 and next_lunar.month == 1 and next_lunar.day == 1:
        festivals.append("除夕")

    return f"农历{prefix}{month_name}{day_name}", festivals


def nth_weekday_of_month(day: date, month: int, weekday: int, nth: int) -> bool:
    if day.month != month or day.weekday() != weekday:
        return False
    return (day.day - 1) // 7 + 1 == nth


def festivals_for(day: date) -> tuple[list[str], str]:
    festivals = list(SOLAR_FESTIVALS.get((day.month, day.day), []))
    if nth_weekday_of_month(day, 5, 6, 2):
        festivals.append("母亲节")
    if nth_weekday_of_month(day, 6, 6, 3):
        festivals.append("父亲节")

    lunar_text, lunar_festivals = lunar_info(day)
    festivals.extend(lunar_festivals)

    unique: list[str] = []
    for festival in festivals:
        if festival not in unique:
            unique.append(festival)
    return unique, lunar_text


def tomorrow_weather_line(config: dict[str, Any]) -> str:
    location = str(config.get("default_weather_location") or "").strip()
    if not location:
        return ""

    try:
        from qq_gemini_bot import ask_weather

        weather = ask_weather(config, f"明天{location}天气怎么样")
    except Exception as exc:
        return f"明天天气：暂时查不到（{exc}）"

    lines = [line.strip() for line in weather.splitlines() if line.strip()]
    if not lines:
        return ""
    return "明天天气：" + "；".join(lines[:3])


def ask_festival_message(config: dict[str, Any], festivals: list[str], tomorrow: date) -> str:
    if not festivals:
        return ""

    try:
        from qq_gemini_bot import ask_model

        copied = dict(config)
        copied["max_output_tokens"] = min(int(copied.get("max_output_tokens") or 700), 180)
        prompt = (
            "你叫温德尔，是一个友好的 QQ 群游戏助手，尤其熟悉 Fortnite / 堡垒之夜，但也能自然聊天。"
            f"明天是 {tomorrow:%Y-%m-%d}，节日/纪念日：{'、'.join(festivals)}。"
            "请用简体中文，结合节日特征和你的游戏助手人设，写 2-4 句睡前群聊提醒。"
            "语气自然一点，可以轻松有趣，但不要油腻，不要太长。"
        )
        return ask_model(copied, prompt).strip()
    except Exception:
        festival_text = "、".join(festivals)
        return f"明天是{festival_text}，温德尔先祝大家节日顺利。今天早点睡，明天再精神满满地开游戏。"


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def game_deal_reminders(now: datetime, threshold_hours: int = 36) -> list[str]:
    threshold = now + timedelta(hours=threshold_hours)
    notes: list[str] = []
    try:
        data = fetch_game_deals(steam_limit=5, epic_country="CN")
    except Exception as exc:
        return [f"游戏优惠：今晚暂时查不到 Steam/Epic 信息（{exc}）。"]

    epic = data.get("epic") if isinstance(data.get("epic"), dict) else {}
    current = epic.get("current") if isinstance(epic.get("current"), list) else []
    ending_epic: list[str] = []
    for item in current:
        if not isinstance(item, dict):
            continue
        end = parse_datetime(str(item.get("end") or ""))
        if not end:
            continue
        end_local = end.astimezone(CHINA_TZ)
        if now < end_local <= threshold:
            title = str(item.get("title") or "未知游戏")
            ending_epic.append(f"Epic《{title}》免费领取将在 {end_local:%m-%d %H:%M} 结束")

    notes.extend(ending_epic[:4])

    steam = data.get("steam") if isinstance(data.get("steam"), list) else []
    if steam:
        top = []
        for item in steam[:3]:
            if isinstance(item, dict):
                top.append(f"{item.get('title')} {item.get('discount')} {item.get('final_price')}")
        if top:
            notes.append("Steam 热销折扣榜：" + "；".join(top) + "。结束时间以 Steam 页面为准。")

    if not notes:
        notes.append("今晚暂时没有发现 Epic 免费游戏临近结束；Steam 折扣可明天发“游戏优惠”查看。")
    return notes


def build_bedtime_message(now: datetime | None = None) -> str:
    now = now.astimezone(CHINA_TZ) if now else datetime.now(CHINA_TZ)
    tomorrow = (now + timedelta(days=1)).date()
    bot_config = load_bot_config()
    festivals, lunar_text = festivals_for(tomorrow)

    lines = [
        "睡觉提醒：已经 23:30 啦，今天先收工，别再开下一把了。",
        f"明天：{tomorrow:%Y年%m月%d日}，{WEEKDAYS[tomorrow.weekday()]}。",
    ]
    if lunar_text:
        lines.append(lunar_text)
    lines.append("节日：" + ("、".join(festivals) if festivals else "明天没有特别节日，适合普通但稳定地变强。"))

    weather = tomorrow_weather_line(bot_config)
    if weather:
        lines.append(weather)

    festival_message = ask_festival_message(bot_config, festivals, tomorrow)
    if festival_message:
        lines.append("")
        lines.append(festival_message)

    deal_notes = game_deal_reminders(now)
    if deal_notes:
        lines.append("")
        lines.append("游戏优惠提醒：")
        lines.extend(f"- {note}" for note in deal_notes)

    lines.append("")
    lines.append("晚安，明天再继续上分。")
    return "\n".join(lines)


def send_group_text(base_url: str, access_token: str, group_id: int | str, text: str) -> None:
    post_onebot(
        base_url=base_url,
        action="send_group_msg",
        payload={"group_id": group_id, "message": [{"type": "text", "data": {"text": text}}]},
        access_token=access_token,
        timeout=120,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a nightly bedtime reminder to QQ groups.")
    parser.add_argument("--config", default=str(QQ_CONFIG_PATH), help="Path to qq_bot_config.json.")
    parser.add_argument("--onebot-url", help="OneBot HTTP URL, for example http://127.0.0.1:3000.")
    parser.add_argument("--access-token", help="OneBot access token, if enabled in NapCatQQ.")
    parser.add_argument("--group-id", action="append", help="QQ group ID. Can be provided multiple times.")
    parser.add_argument("--dry-run", action="store_true", help="Print message without sending.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    base_url = normalize_base_url(args.onebot_url or str(config.get("onebot_http_url") or "http://127.0.0.1:3000"))
    group_ids = normalize_group_ids(args.group_id or config.get("group_ids"))
    access_token = args.access_token
    if access_token is None:
        access_token = str(config.get("access_token") or "")

    message = build_bedtime_message()
    if args.dry_run:
        print(message)
        print(f"Groups: {group_ids}")
        return 0

    for group_id in group_ids:
        send_group_text(base_url, access_token, group_id, message)
        print(f"Sent bedtime reminder to group {group_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
