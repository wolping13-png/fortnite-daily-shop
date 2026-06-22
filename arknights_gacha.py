from __future__ import annotations

import json
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "bot_memory" / "arknights_gacha.json"
OUTPUT_DIR = BASE_DIR / "bot_memory" / "arknights_gacha_images"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
STATE_LOCK = threading.RLock()

MAX_PULLS_PER_COMMAND = 300
HISTORY_LIMIT = 120

# Operator pool adapted from https://github.com/aynuzbh/koishi-plugin-arknights-card (MIT License).
# This module keeps the data local and framework-free so it can run inside the NapCat bot.
LIMITED_OPERATORS = [
    "6|武者|黑泠",
    "6|重射手|白瑾",
    "6|极寒术师|霜星",
    "6|怪杰|新约能天使",
    "6|战术家|缪尔赛思",
    "6|驭械术师|荒芜拉普兰德",
    "6|投掷手|维什戴尔",
    "6|扩散术师|玛露西尔",
    "6|处决者|弑君者",
    "6|守护者|黍",
    "6|巫役|塑心",
    "6|行医|纯烬艾雅法拉",
    "6|处决者|缄默德克萨斯",
    "6|处决者|麒麟R夜刀",
    "6|斗士|重岳",
    "6|召唤师|令",
    "6|无畏者|耀骑士临光",
    "6|散射手|假日威龙陈",
    "6|吟游者|浊心斯卡蒂",
    "6|速射手|灰烬",
    "6|投掷手|迷迭香",
    "6|炮手|W",
    "6|铁卫|年",
]

SIX_STAR_OPERATORS = [
    "6|神射手|蕾缪安",
    "6|链愈师|Mon3tr",
    "6|塑灵术师|死芒",
    "6|本源术师|烛煌",
    "6|炼金师|引星棘刺",
    "6|尖兵|忍冬",
    "6|术战者|维娜维多利亚",
    "6|本源术师|妮芙",
    "6|重剑手|乌尔比安",
    "6|中坚术师|逻各斯",
    "6|伏击客|阿斯卡纶",
    "6|武者|左乐",
    "6|剑豪|锏",
    "6|术战者|薇薇安娜",
    "6|重剑手|赫德雷",
    "6|哨戒铁卫|涤火杰西卡",
    "6|行商|琳琅诗怀雅",
    "6|攻城手|提丰",
    "6|收割者|圣约送葬人",
    "6|中坚术师|霍尔海雅",
    "6|情报官|伊内丝",
    "6|领主|仇白",
    "6|阵法术师|林",
    "6|咒愈师|焰影苇草",
    "6|不屈者|斥罪",
    "6|工匠|白铁",
    "6|武者|赫拉格",
    "6|扩散术师|莫斯提马",
    "6|召唤师|麦哲伦",
    "6|怪杰|阿",
    "6|攻城手|煌",
    "6|中坚术师|刻俄柏",
    "6|处决者|傀影",
    "6|冲锋手|风笛",
    "6|推击手|温蒂",
    "6|攻城手|早露",
    "6|滞凝师|铃兰",
    "6|领主|棘刺",
    "6|术战者|史尔特尔",
    "6|不屈者|泥岩",
    "6|斗士|山",
    "6|速射手|空弦",
    "6|尖兵|嵯峨",
    "6|医师|凯尔希",
    "6|执旗手|琴柳",
    "6|解放者|玛恩纳",
    "6|速射手|能天使",
    "6|轰击术师|伊芙利特",
    "6|中坚术师|艾雅法拉",
    "6|尖兵|推进之王",
    "6|凝滞师|安洁莉娜",
    "6|医师|闪灵",
    "6|群愈师|夜莺",
    "6|铁卫|星熊",
    "6|守护者|塞雷娅",
    "6|领主|银灰",
    "6|无畏者|斯卡蒂",
    "6|剑豪|陈",
    "6|重射手|黑",
]

FIVE_STAR_OPERATORS = [
    "5|异格职业|阿米娅",
    "5|本源术师|克里斯汀",
    "5|巡空者|蒂比",
    "5|工匠|阿兰娜",
    "5|回环射手|水灯心",
    "5|疗养师|诺威尔",
    "5|指挥官|寻澜",
    "5|护佑者|行箸",
    "5|巫役|波卜",
    "5|无畏者|莱欧斯",
    "5|情报官|齐尔查克",
    "5|守护者|森西",
    "5|召唤师|衡沙",
    "5|链愈师|莎草",
    "5|战术家|渡桥",
    "5|削弱者|海霓",
    "5|冲锋手|历阵锐枪芬",
    "5|轰击术师|阿罗玛",
    "5|教官|医生",
    "5|傀儡师|双月",
    "5|强攻手|导火索",
    "5|尖兵|红隼",
    "5|执旗手|万顷",
    "5|领主|烈夏",
    "5|咒愈师|刺玫",
    "5|秘术师|戴菲恩",
    "5|猎手|冰酿",
    "5|巫役|凛视",
    "5|扩散术师|寒檀",
    "5|速射手|隐现",
    "5|无畏者|摩根",
    "5|武者|火龙S黑角",
    "5|神射手|子月",
    "5|链愈师|明椒",
    "5|斗士|达格达",
    "5|情报官|晓歌",
    "5|投掷手|承曦格雷伊",
    "5|咒愈师|曜尘芙蓉",
    "5|攻城手|埃托拉",
    "5|吟游者|海蒂",
    "5|傀儡师|风丸",
    "5|战术家|夜半",
    "5|速射手|寒芒克洛丝",
    "5|护佑者|九色鹿",
    "5|决战者|极光",
    "5|冲锋手|野鬃",
    "5|收割者|羽毛笔",
    "5|伏击客|绮良",
    "5|武者|赤冬",
    "5|铁卫|暴雨",
    "5|哨戒铁卫|闪击",
    "5|行商|乌有",
    "5|扩散术师|炎狱炎熔",
    "5|处决者|卡夫卡",
    "5|陷阱师|罗宾",
    "5|速射手|四月",
    "5|斗士|燧石",
    "5|尖兵|贾维",
    "5|召唤师|稀音",
    "5|执旗手|极境",
    "5|削弱者|巫恋",
    "5|炮手|慑砂",
    "5|剑豪|柏喙",
    "5|守护者|吽",
    "5|速射手|灰喉",
    "5|冲锋手|苇草",
    "5|强攻手|布洛卡",
    "5|处决者|槐琥",
    "5|无畏者|炎客",
    "5|术战者|星极",
    "5|散射手|送葬人",
    "5|滞凝师|格劳克斯",
    "5|教官|诗怀雅",
    "5|强攻手|暴行",
    "5|伏击客|狮蝎",
    "5|吟游者|空",
    "5|削弱者|初雪",
    "5|重射手|普罗旺斯",
    "5|铁卫|可颂",
    "5|处决者|红",
    "5|哨戒铁卫|雷蛇",
    "5|守护者|临光",
    "5|医师|华法琳",
    "5|医师|赫默",
    "5|扩散术师|天火",
    "5|速射手|蓝毒",
    "5|领主|拉普兰德",
    "5|强攻手|幽灵鲨",
    "5|尖兵|德克萨斯",
    "5|群愈师|白面鸮",
]

FOUR_STAR_OPERATORS = [
    "4|巡空者|云迹",
    "4|解放者|骋风",
    "4|不屈者|露托",
    "4|回环射手|跃跃",
    "4|收割者|休谟斯",
    "4|重剑手|石英",
    "4|攻城手|铅踝",
    "4|领主|罗小黑",
    "4|链术师|布丁",
    "4|行医|褐果",
    "4|秘术师|深靛",
    "4|工匠|罗比菈塔",
    "4|战术家|豆苗",
    "4|散射手|松果",
    "4|铁卫|泡泡",
    "4|斗士|杰克",
    "4|领主|芳汀",
    "4|驭械术师|卡达",
    "4|重射手|酸糖",
    "4|剑豪|刻刀",
    "4|行商|孑",
    "4|无畏者|断罪者",
    "4|滞凝师|波登可",
    "4|武者|宴",
    "4|神射手|安比尔",
    "4|速射手|梅",
    "4|伏击客|伊桑",
    "4|执旗手|桃金娘",
    "4|医师|苏苏洛",
    "4|扩散术师|格雷伊",
    "4|斗士|猎蜂",
    "4|推击手|阿消",
    "4|凝滞师|地灵",
    "4|召唤师|深海色",
    "4|守护者|古米",
    "4|铁卫|角峰",
    "4|铁卫|蛇屠箱",
    "4|医师|嘉维尔",
    "4|群愈师|调香师",
    "4|医师|末药",
    "4|钩索师|暗索",
    "4|术战者|慕斯",
    "4|处决者|砾",
    "4|领主|霜叶",
    "4|强攻手|艾丝黛尔",
    "4|无畏者|缠丸",
]

THREE_STAR_OPERATORS = [
    "3|守护者|斑点",
    "3|强攻手|泡普卡",
    "3|领主|月见夜",
    "3|炮手|空爆",
    "3|中坚术师|史都华德",
    "3|凝滞师|梓兰",
    "3|医师|安赛尔",
    "3|医师|芙蓉",
    "3|扩散术师|炎熔",
    "3|速射手|安德切尔",
    "3|铁卫|米格鲁",
    "3|无畏者|玫兰莎",
    "3|铁卫|卡缇",
    "3|冲锋手|翎羽",
    "3|尖兵|香草",
    "3|尖兵|芬",
    "3|速射手|克洛丝",
]


def parse_operator(value: str, limited: bool = False) -> dict[str, Any]:
    rarity, profession, name = value.split("|", 2)
    return {
        "rarity": int(rarity),
        "profession": profession,
        "name": name,
        "limited": limited,
    }


POOLS = {
    6: [parse_operator(item) for item in SIX_STAR_OPERATORS],
    5: [parse_operator(item) for item in FIVE_STAR_OPERATORS],
    4: [parse_operator(item) for item in FOUR_STAR_OPERATORS],
    3: [parse_operator(item) for item in THREE_STAR_OPERATORS],
}
LIMITED_POOL = [parse_operator(item, limited=True) for item in LIMITED_OPERATORS]

BANNERS: dict[str, dict[str, Any]] = {
    "standard": {
        "title": "标准寻访",
        "aliases": ("标准", "常驻", "普通", "默认", "标准池", "常驻池"),
        "description": "常驻模拟池，六星有 50% 概率落在展示 UP。",
        "six_up": ("能天使", "银灰"),
        "five_up": ("德克萨斯", "白面鸮", "拉普兰德"),
        "limited": False,
    },
    "limited": {
        "title": "限定寻访",
        "aliases": ("限定", "限定池", "限定寻访", "周年", "夏活", "春节"),
        "description": "限定模拟池，六星更容易落在限定 / 展示 UP。",
        "six_up": ("新约能天使", "荒芜拉普兰德", "维什戴尔", "玛露西尔"),
        "five_up": ("历阵锐枪芬", "承曦格雷伊", "濯尘芙蓉"),
        "limited": True,
    },
    "kernel": {
        "title": "中坚寻访",
        "aliases": ("中坚", "中坚池", "经典", "经典池", "老池"),
        "description": "中坚模拟池，偏早期常驻干员。",
        "six_up": ("能天使", "银灰", "艾雅法拉", "推进之王", "星熊"),
        "five_up": ("德克萨斯", "白面鸮", "蓝毒", "天火", "拉普兰德"),
        "limited": False,
    },
}
BANNER_ORDER = ("standard", "limited", "kernel")


def banner_config(banner_key: str) -> dict[str, Any]:
    return BANNERS.get(banner_key, BANNERS["standard"])


def banner_title(banner_key: str) -> str:
    return str(banner_config(banner_key).get("title") or "标准寻访")


def resolve_banner_key_from_text(text: str, default: str = "") -> str:
    compact = re.sub(r"\s+", "", str(text or "").lower())
    for key, data in BANNERS.items():
        aliases = data.get("aliases") or ()
        if key in compact:
            return key
        for alias in aliases:
            if str(alias).lower() in compact:
                return key
    return default


def operator_matches_name(operator: dict[str, Any], name: str) -> bool:
    value = str(name or "").strip()
    return bool(value) and value in str(operator.get("name") or "")


def find_operator_by_name(name: str, rarity: int | None = None) -> dict[str, Any] | None:
    pools: list[dict[str, Any]] = []
    if rarity is None or rarity == 6:
        pools.extend(LIMITED_POOL)
    if rarity is None:
        for items in POOLS.values():
            pools.extend(items)
    else:
        pools.extend(POOLS.get(rarity, []))

    for operator in pools:
        if operator_matches_name(operator, name):
            return dict(operator)
    return None


def choose_up_operator(names: tuple[str, ...], rarity: int) -> dict[str, Any] | None:
    candidates = [item for name in names if (item := find_operator_by_name(name, rarity=rarity))]
    if not candidates:
        return None
    return dict(random.choice(candidates))


def banner_list_text(selected_banner: str) -> str:
    lines = ["方舟可选卡池：", "━━━━━━"]
    for key in BANNER_ORDER:
        data = banner_config(key)
        marker = "当前" if key == selected_banner else "可选"
        lines.append(f"- {data['title']}（{marker}）：{data['description']}")
    lines.append("用法：方舟卡池 限定 / 方舟卡池 标准 / 方舟卡池 中坚")
    lines.append("也可以直接说：方舟限定十连、方舟中坚抽卡50。")
    return "\n".join(lines)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"users": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    return data


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def default_user_state() -> dict[str, Any]:
    return {
        "pity": 0,
        "guarantee_remaining": 10,
        "total": 0,
        "counts": {"6": 0, "5": 0, "4": 0, "3": 0},
        "limited_count": 0,
        "selected_banner": "standard",
        "history": [],
        "updated_at": "",
    }


def get_user_state(data: dict[str, Any], user_key: str) -> dict[str, Any]:
    users = data.setdefault("users", {})
    state = users.get(user_key)
    if not isinstance(state, dict):
        state = default_user_state()
        users[user_key] = state
    state.setdefault("pity", 0)
    state.setdefault("guarantee_remaining", 10)
    state.setdefault("total", 0)
    state.setdefault("counts", {"6": 0, "5": 0, "4": 0, "3": 0})
    state.setdefault("limited_count", 0)
    state.setdefault("selected_banner", "standard")
    state.setdefault("history", [])
    return state


def six_star_rate(pity: int) -> float:
    pity = max(0, int(pity or 0))
    if pity < 50:
        return 2.0
    return min(100.0, 2.0 + (pity - 49) * 2.0)


def choose_operator(rarity: int, banner_key: str = "standard") -> dict[str, Any]:
    banner = banner_config(banner_key)
    if rarity == 6:
        up = choose_up_operator(tuple(banner.get("six_up") or ()), rarity=6)
        up_chance = 0.7 if banner.get("limited") else 0.5
        if up and random.random() < up_chance:
            return up
        if banner.get("limited") and LIMITED_POOL and random.random() < 0.35:
            return dict(random.choice(LIMITED_POOL))
    if rarity == 5:
        up = choose_up_operator(tuple(banner.get("five_up") or ()), rarity=5)
        if up and random.random() < 0.5:
            return up
    return dict(random.choice(POOLS[rarity]))


def roll_once(state: dict[str, Any], banner_key: str = "standard") -> dict[str, Any]:
    pity = int(state.get("pity") or 0)
    guarantee_remaining = int(state.get("guarantee_remaining") or 0)
    rate_6 = six_star_rate(pity)
    roll = random.random() * 100

    if roll < rate_6:
        rarity = 6
    elif guarantee_remaining == 1:
        rarity = 5
    elif roll < rate_6 + 8:
        rarity = 5
    elif roll < rate_6 + 8 + 50:
        rarity = 4
    else:
        rarity = 3

    operator = choose_operator(rarity, banner_key=banner_key)
    if rarity == 6:
        state["pity"] = 0
    else:
        state["pity"] = pity + 1

    if guarantee_remaining > 0:
        if rarity >= 5:
            state["guarantee_remaining"] = 0
        else:
            state["guarantee_remaining"] = guarantee_remaining - 1

    counts = state.setdefault("counts", {"6": 0, "5": 0, "4": 0, "3": 0})
    counts[str(rarity)] = int(counts.get(str(rarity), 0)) + 1
    state["total"] = int(state.get("total") or 0) + 1
    if operator.get("limited"):
        state["limited_count"] = int(state.get("limited_count") or 0) + 1

    result = {
        "rarity": rarity,
        "profession": operator["profession"],
        "name": operator["name"],
        "limited": bool(operator.get("limited")),
        "banner": banner_key,
        "rate_6": rate_6,
        "pity_before": pity,
    }
    history = state.setdefault("history", [])
    history.insert(
        0,
        {
            **result,
            "time": datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    state["history"] = history[:HISTORY_LIMIT]
    state["updated_at"] = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return result


def star_text(rarity: int) -> str:
    return "★" * rarity


def format_operator(result: dict[str, Any]) -> str:
    label = f"{star_text(int(result['rarity']))} {result['profession']} {result['name']}"
    if result.get("limited"):
        label = f"【限定】{label}"
    return label


def summarize_results(results: list[dict[str, Any]], state: dict[str, Any], nickname: str, banner_key: str) -> str:
    count = len(results)
    title = banner_title(banner_key)
    lines = [f"{nickname or '博士'}，{title}结果：", "━━━━━━"]

    if count <= 10:
        lines.extend(format_operator(result) for result in results)
    else:
        rare = [result for result in results if int(result["rarity"]) >= 5 or result.get("limited")]
        if rare:
            lines.append("高星结果：")
            lines.extend(format_operator(result) for result in rare[:30])
            if len(rare) > 30:
                lines.append(f"...还有 {len(rare) - 30} 个五星以上结果")
        else:
            lines.append("这次没有五星以上，背包有点安静。")

    summary_counts = {rarity: sum(1 for result in results if int(result["rarity"]) == rarity) for rarity in (6, 5, 4, 3)}
    limited_count = sum(1 for result in results if result.get("limited"))
    lines.append("━━━━━━")
    lines.append(
        f"本次：六星 {summary_counts[6]} / 五星 {summary_counts[5]} / "
        f"四星 {summary_counts[4]} / 三星 {summary_counts[3]}"
    )
    if limited_count:
        lines.append(f"限定干员：{limited_count} 个")
    next_rate = six_star_rate(int(state.get("pity") or 0))
    lines.append(f"距离上次六星：{int(state.get('pity') or 0)} 抽；当前六星率：{next_rate:.0f}%")
    if int(state.get("guarantee_remaining") or 0) > 0:
        lines.append(f"前十保底剩余：{int(state.get('guarantee_remaining') or 0)} 抽")
    return "\n".join(lines)


def format_status(state: dict[str, Any], nickname: str) -> str:
    counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
    total = int(state.get("total") or 0)
    lines = [
        f"{nickname or '博士'}的方舟寻访记录：",
        "━━━━━━",
        f"总抽数：{total}",
        f"六星：{int(counts.get('6') or 0)}",
        f"五星：{int(counts.get('5') or 0)}",
        f"四星：{int(counts.get('4') or 0)}",
        f"三星：{int(counts.get('3') or 0)}",
        f"限定：{int(state.get('limited_count') or 0)}",
        f"当前卡池：{banner_title(str(state.get('selected_banner') or 'standard'))}",
        f"距离上次六星：{int(state.get('pity') or 0)} 抽",
        f"当前六星率：{six_star_rate(int(state.get('pity') or 0)):.0f}%",
    ]
    recent = state.get("history") if isinstance(state.get("history"), list) else []
    rare_recent = [item for item in recent if int(item.get("rarity") or 0) >= 5][:8]
    if rare_recent:
        lines.append("最近高星：")
        lines.extend(f"- {format_operator(item)}" for item in rare_recent)
    return "\n".join(lines)


def load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            if candidate and Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def fit_text(draw: Any, text: str, font: Any, max_width: int) -> str:
    value = str(text or "").strip()
    if text_size(draw, value, font)[0] <= max_width:
        return value
    while value and text_size(draw, f"{value}...", font)[0] > max_width:
        value = value[:-1]
    return f"{value}..." if value else "..."


def rarity_colors(rarity: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    return {
        6: ((246, 171, 52), (130, 69, 20)),
        5: ((232, 204, 84), (111, 90, 28)),
        4: ((168, 108, 226), (72, 49, 124)),
        3: ((93, 157, 230), (30, 75, 130)),
    }.get(rarity, ((132, 143, 160), (47, 55, 68)))


def draw_operator_card(draw: Any, box: tuple[int, int, int, int], result: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    rarity = int(result.get("rarity") or 3)
    light, dark = rarity_colors(rarity)
    card_bg = tuple(max(0, int(channel * 0.72)) for channel in dark)
    draw.rounded_rectangle((x1 + 5, y1 + 7, x2 + 5, y2 + 7), radius=18, fill=(0, 0, 0, 80))
    draw.rounded_rectangle(box, radius=18, fill=card_bg, outline=light, width=3)
    draw.rounded_rectangle((x1, y1, x2, y1 + 14), radius=16, fill=light)

    star = "★" * rarity
    draw.text((x1 + 20, y1 + 26), star, fill=(255, 248, 210), font=load_font(25, True))

    name = fit_text(draw, str(result.get("name") or "未知干员"), load_font(31, True), x2 - x1 - 40)
    profession = fit_text(draw, str(result.get("profession") or "未知职业"), load_font(19), x2 - x1 - 40)
    draw.text((x1 + 20, y1 + 67), name, fill=(255, 255, 255), font=load_font(31, True))
    draw.text((x1 + 21, y1 + 109), profession, fill=(212, 226, 244), font=load_font(19))

    if result.get("limited"):
        tag = "限定"
        tw, th = text_size(draw, tag, load_font(17, True))
        draw.rounded_rectangle((x2 - tw - 42, y1 + 24, x2 - 18, y1 + 52), radius=12, fill=(241, 78, 101))
        draw.text((x2 - tw - 30, y1 + 28), tag, fill=(255, 255, 255), font=load_font(17, True))


def format_pull_caption(results: list[dict[str, Any]], state: dict[str, Any], nickname: str, banner_key: str) -> str:
    counts = {rarity: sum(1 for result in results if int(result["rarity"]) == rarity) for rarity in (6, 5, 4, 3)}
    rare = [result for result in results if int(result.get("rarity") or 0) >= 5]
    rare_text = "、".join(str(item.get("name") or "") for item in rare[:4])
    if len(rare) > 4:
        rare_text += f" 等 {len(rare)} 个高星"
    if not rare_text:
        rare_text = "这次没有五星以上"
    return (
        f"{nickname or '博士'}，{banner_title(banner_key)} {len(results)} 抽结果来了。\n"
        f"六星 {counts[6]} / 五星 {counts[5]} / 四星 {counts[4]} / 三星 {counts[3]}；{rare_text}。\n"
        f"当前距离六星 {int(state.get('pity') or 0)} 抽。"
    )


def render_gacha_image(results: list[dict[str, Any]], state: dict[str, Any], nickname: str, banner_key: str) -> Path:
    from PIL import Image, ImageDraw

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    width = 1080
    padding = 42
    header_h = 170
    card_w = 312
    card_h = 154
    gap = 24
    cols = 3

    visible = list(results)
    if len(results) > 10:
        rare = [item for item in results if int(item.get("rarity") or 0) >= 5 or item.get("limited")]
        visible = rare[:24] if rare else results[:12]

    rows = max(1, (len(visible) + cols - 1) // cols)
    footer_h = 116
    height = padding + header_h + rows * card_h + max(0, rows - 1) * gap + footer_h + padding
    image = Image.new("RGB", (width, height), (14, 20, 33))
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(height):
        blend = y / max(1, height - 1)
        color = (
            int(13 + 18 * blend),
            int(21 + 25 * blend),
            int(38 + 35 * blend),
        )
        draw.line((0, y, width, y), fill=color)

    title_font = load_font(48, True)
    subtitle_font = load_font(21)
    small_font = load_font(17)
    badge_font = load_font(18, True)

    title = f"{banner_title(banner_key)} · {len(results)} 抽"
    draw.text((padding, padding + 5), title, fill=(255, 255, 255), font=title_font)
    now = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M")
    draw.text((padding, padding + 68), f"{nickname or '博士'} · {now}", fill=(159, 188, 218), font=subtitle_font)

    counts = {rarity: sum(1 for result in results if int(result["rarity"]) == rarity) for rarity in (6, 5, 4, 3)}
    badges = [
        f"6★ {counts[6]}",
        f"5★ {counts[5]}",
        f"4★ {counts[4]}",
        f"3★ {counts[3]}",
        f"保底 {int(state.get('pity') or 0)}",
    ]
    x = padding
    y = padding + 110
    for badge in badges:
        tw, th = text_size(draw, badge, badge_font)
        draw.rounded_rectangle((x, y, x + tw + 26, y + 34), radius=16, fill=(33, 49, 75), outline=(85, 119, 161))
        draw.text((x + 13, y + 6), badge, fill=(247, 222, 128), font=badge_font)
        x += tw + 38

    start_y = padding + header_h
    start_x = padding
    for index, result in enumerate(visible):
        row = index // cols
        col = index % cols
        x1 = start_x + col * (card_w + gap)
        y1 = start_y + row * (card_h + gap)
        draw_operator_card(draw, (x1, y1, x1 + card_w, y1 + card_h), result)

    footer_y = height - padding - footer_h + 22
    if len(results) > len(visible):
        note = f"本次共 {len(results)} 抽，图片只展示高星 / 前 {len(visible)} 个结果。完整统计已计入记录。"
    else:
        note = "模拟寻访结果，仅用于娱乐；实际卡池和概率请以游戏内公告为准。"
    draw.text((padding, footer_y), note, fill=(151, 175, 202), font=small_font)
    draw.text(
        (padding, footer_y + 34),
        f"当前卡池：{banner_title(str(state.get('selected_banner') or banner_key))} · 当前六星率 {six_star_rate(int(state.get('pity') or 0)):.0f}%",
        fill=(151, 175, 202),
        font=small_font,
    )

    safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(nickname or "doctor"))[:24] or "doctor"
    target = OUTPUT_DIR / f"arknights_{int(time.time())}_{safe_key}_{random.randint(1000, 9999)}.jpg"
    image.save(target, quality=90, optimize=True)
    return target


def parse_command(text: str) -> dict[str, Any] | None:
    value = text.strip()
    compact = re.sub(r"\s+", "", value.lower())
    if not any(mark in compact for mark in ("方舟", "明日方舟", "arknights")):
        return None

    banner_key = resolve_banner_key_from_text(compact)
    if "卡池" in compact or "池子" in compact:
        if banner_key:
            return {"action": "select_banner", "banner": banner_key}
        return {"action": "banners"}
    if any(word in compact for word in ("选择", "切换", "换成", "设为")) and banner_key:
        return {"action": "select_banner", "banner": banner_key}

    if any(word in compact for word in ("状态", "查询", "统计", "记录")):
        return {"action": "status"}
    if any(word in compact for word in ("重置", "清空", "清除")):
        return {"action": "reset"}

    if "来一井" in compact or "一井" in compact:
        return {"action": "pull", "count": 300, "banner": banner_key}
    if "十连" in compact or "10连" in compact:
        return {"action": "pull", "count": 10, "banner": banner_key}
    if "单抽" in compact or "一抽" in compact:
        return {"action": "pull", "count": 1, "banner": banner_key}

    match = re.search(r"(?:抽卡|寻访|抽)(\d{1,3})", compact)
    if match:
        count = max(1, min(int(match.group(1)), MAX_PULLS_PER_COMMAND))
        return {"action": "pull", "count": count, "banner": banner_key}

    if any(word in compact for word in ("抽卡", "寻访", "抽")):
        return {"action": "pull", "count": 10, "banner": banner_key}

    if compact in {"方舟", "明日方舟", "arknights"}:
        return {"action": "help"}
    return None


def looks_like_command(text: str) -> bool:
    return parse_command(text) is not None


def handle_command_payload(text: str, user_key: str, nickname: str = "") -> tuple[str, Path | None, str]:
    command = parse_command(text)
    if not command:
        return "", None, ""

    with STATE_LOCK:
        data = load_state()
        state = get_user_state(data, user_key)

        action = command["action"]
        if action == "help":
            answer = (
                "方舟寻访用法：方舟单抽 / 方舟十连 / 方舟抽卡 50 / 方舟来一井 / "
                "方舟限定十连 / 方舟中坚抽卡50 / 方舟卡池 / 方舟卡池 限定 / 方舟状态 / 方舟重置"
            )
            return answer, None, answer
        if action == "banners":
            answer = banner_list_text(str(state.get("selected_banner") or "standard"))
            return answer, None, answer
        if action == "select_banner":
            banner_key = str(command.get("banner") or "standard")
            state["selected_banner"] = banner_key
            save_state(data)
            answer = f"已切换到 {banner_title(banner_key)}。下次不写卡池时，就默认抽这个池。"
            return answer, None, answer
        if action == "status":
            answer = format_status(state, nickname)
            return answer, None, answer
        if action == "reset":
            data.setdefault("users", {})[user_key] = default_user_state()
            save_state(data)
            answer = "方舟寻访记录已重置。新的前十保底也重新开始了。"
            return answer, None, answer

        count = int(command.get("count") or 10)
        banner_key = str(command.get("banner") or state.get("selected_banner") or "standard")
        if banner_key not in BANNERS:
            banner_key = "standard"
        results = [roll_once(state, banner_key=banner_key) for _ in range(count)]
        save_state(data)
        fallback_text = summarize_results(results, state, nickname, banner_key)
        caption = format_pull_caption(results, state, nickname, banner_key)
        image_path = render_gacha_image(results, state, nickname, banner_key)
        return caption, image_path, fallback_text


def handle_command(text: str, user_key: str, nickname: str = "") -> str:
    caption, _image_path, fallback_text = handle_command_payload(text, user_key, nickname)
    return fallback_text or caption


if __name__ == "__main__":
    print(handle_command("方舟十连", "local:test", "博士"))
