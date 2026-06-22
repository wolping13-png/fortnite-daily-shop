from __future__ import annotations

import json
import hashlib
import html
import random
import re
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "bot_memory" / "arknights_gacha.json"
OUTPUT_DIR = BASE_DIR / "bot_memory" / "arknights_gacha_images"
OFFICIAL_GACHA_DATA_PATH = BASE_DIR / "data" / "arknights_gacha_official.json"
ASSET_DIR = BASE_DIR / "assets" / "akgacha"
PORTRAIT_DIR = BASE_DIR / "bot_memory" / "arknights_gacha_assets" / "half"
PRTS_HALF_MAP_PATH = BASE_DIR / "bot_memory" / "arknights_prts_halves.json"
PRTS_OPERATOR_LIST_URL = "https://prts.wiki/w/%E5%B9%B2%E5%91%98%E4%B8%80%E8%A7%88"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
STATE_LOCK = threading.RLock()

MAX_PULLS_PER_COMMAND = 300
HISTORY_LIMIT = 120
BANNER_CATALOG_TTL_SECONDS = 30 * 60
HIDDEN_CATALOG_RULE_TYPES = {"BACKFLOW", "CLASSIC", "CLASSIC_DOUBLE", "FESCLASSIC", "SPECIAL"}
HIDDEN_CATALOG_TITLE_PREFIXES = ("普池#", "适合多种场合")
HIDDEN_CATALOG_TITLE_KEYWORDS = ("联合行动", "定向甄选", "归航寻访")

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


@lru_cache(maxsize=1)
def load_official_gacha_data() -> dict[str, Any]:
    if not OFFICIAL_GACHA_DATA_PATH.exists():
        return {"banners": [], "operators": []}
    try:
        data = json.loads(OFFICIAL_GACHA_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"banners": [], "operators": []}
    if not isinstance(data, dict):
        return {"banners": [], "operators": []}
    data.setdefault("banners", [])
    data.setdefault("operators", [])
    return data


def official_banner_records() -> list[dict[str, Any]]:
    records = load_official_gacha_data().get("banners")
    return records if isinstance(records, list) else []


def is_catalog_up_banner(item: dict[str, Any]) -> bool:
    rule_type = str(item.get("rule_type") or "")
    if rule_type in HIDDEN_CATALOG_RULE_TYPES:
        return False
    title = str(item.get("title") or "")
    if not item.get("key") or not title:
        return False
    if title.startswith(HIDDEN_CATALOG_TITLE_PREFIXES):
        return False
    if any(keyword in title for keyword in HIDDEN_CATALOG_TITLE_KEYWORDS):
        return False
    return True


def catalog_up_banner_records() -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in official_banner_records():
        if not isinstance(item, dict) or not is_catalog_up_banner(item):
            continue
        key = (str(item.get("open_date") or ""), str(item.get("title") or ""))
        existing = selected.get(key)
        if not existing or catalog_record_priority(item) > catalog_record_priority(existing):
            selected[key] = item
    return list(selected.values())


def catalog_record_priority(item: dict[str, Any]) -> int:
    rule_type = str(item.get("rule_type") or "")
    if rule_type == "LEGACY_LIMITED":
        return 50
    if rule_type.startswith("LEGACY"):
        return 40
    if rule_type in {"LIMITED", "LINKAGE"}:
        return 45
    return 10


@lru_cache(maxsize=1)
def official_banners_by_key() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in official_banner_records():
        if isinstance(item, dict) and item.get("key"):
            result[str(item["key"])] = item
    return result


def official_operator_pool(rarity: int) -> list[dict[str, Any]]:
    operators = load_official_gacha_data().get("operators")
    if not isinstance(operators, list):
        return []
    result: list[dict[str, Any]] = []
    for item in operators:
        if not isinstance(item, dict) or int(item.get("rarity") or 0) != rarity:
            continue
        result.append(
            {
                "rarity": rarity,
                "profession": str(item.get("profession") or "干员"),
                "name": str(item.get("name") or ""),
                "limited": False,
            }
        )
    return [item for item in result if item["name"]]


def combined_operator_pool(rarity: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in [*POOLS.get(rarity, []), *official_operator_pool(rarity)]:
        name = str(item.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(dict(item))
    return result or POOLS.get(rarity, [])


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def clean_banner_query(text: str) -> str:
    compact = compact_text(text)
    compact = re.sub(r"(抽卡|寻访|抽)\d{1,3}", "", compact)
    for token in (
        "明日方舟",
        "arknights",
        "方舟",
        "卡池",
        "池子",
        "选择",
        "切换",
        "换成",
        "设为",
        "十连",
        "10连",
        "单抽",
        "一抽",
        "抽卡",
        "寻访",
        "来一井",
        "一井",
        "列表",
        "搜索",
        "查找",
    ):
        compact = compact.replace(token, "")
    compact = re.sub(r"\d{1,3}$", "", compact)
    compact = re.sub(r"\d{4}[-年]?\d{0,2}[-月]?\d{0,2}日?", "", compact)
    return compact.strip()


def banner_search_blob(item: dict[str, Any]) -> str:
    names: list[str] = []
    for key in ("title", "key", "pool_id", "rule_type", "open_date", "end_date"):
        names.append(str(item.get(key) or ""))
    for key in ("up_6", "up_5", "up_4"):
        values = item.get(key)
        if isinstance(values, list):
            names.extend(str(value) for value in values)
    return compact_text(" ".join(names))


def latest_known_official_banner() -> dict[str, Any] | None:
    records = catalog_up_banner_records()
    if not records:
        return None
    return max(records, key=lambda item: int(item.get("open_time") or 0))


def current_or_latest_official_banner() -> dict[str, Any] | None:
    now = int(time.time())
    active = [
        item
        for item in catalog_up_banner_records()
        if int(item.get("open_time") or 0) <= now <= int(item.get("end_time") or 0)
    ]
    if active:
        return max(active, key=lambda item: int(item.get("open_time") or 0))
    return latest_known_official_banner()


def find_official_banner_matches(query: str, limit: int = 10) -> list[dict[str, Any]]:
    q = clean_banner_query(query)
    if q in {"最新", "最近", "当前", "现在", "本期"}:
        item = current_or_latest_official_banner()
        return [item] if item else []
    if not q:
        return []

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for item in catalog_up_banner_records():
        title = compact_text(str(item.get("title") or ""))
        blob = banner_search_blob(item)
        score = 0
        if compact_text(str(item.get("key") or "")) == q:
            score = 100
        elif title == q:
            score = 95
        elif q in title:
            score = 80
        elif q in blob:
            score = 55
        if score:
            scored.append((score, int(item.get("open_time") or 0), item))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _score, _open_time, item in scored[:limit]]


def banner_config(banner_key: str) -> dict[str, Any]:
    if banner_key in BANNERS:
        return BANNERS[banner_key]
    official = official_banners_by_key().get(str(banner_key))
    if official:
        title = str(official.get("title") or "官方UP池")
        rule_type = str(official.get("rule_type") or "")
        return {
            "title": title,
            "aliases": (title, str(official.get("key") or "")),
            "description": f"{official.get('open_date') or '?'} - {official.get('end_date') or '?'}",
            "six_up": tuple(official.get("up_6") or ()),
            "five_up": tuple(official.get("up_5") or ()),
            "four_up": tuple(official.get("up_4") or ()),
            "limited": bool(official.get("limited")),
            "official": True,
            "legacy": rule_type.startswith("LEGACY"),
            "key": str(official.get("key") or banner_key),
        }
    return BANNERS["standard"]


def banner_title(banner_key: str) -> str:
    return str(banner_config(banner_key).get("title") or "标准寻访")


def resolve_banner_key_from_text(text: str, default: str = "") -> str:
    compact = compact_text(text)
    for key, data in BANNERS.items():
        aliases = data.get("aliases") or ()
        if key in compact:
            return key
        for alias in aliases:
            if str(alias).lower() in compact:
                return key
    matches = find_official_banner_matches(compact, limit=1)
    if matches:
        return str(matches[0].get("key") or "")
    return default


def operator_matches_name(operator: dict[str, Any], name: str) -> bool:
    value = str(name or "").strip()
    return bool(value) and value in str(operator.get("name") or "")


def find_operator_by_name(name: str, rarity: int | None = None) -> dict[str, Any] | None:
    pools: list[dict[str, Any]] = []
    if rarity is None or rarity == 6:
        pools.extend(LIMITED_POOL)
    if rarity is None:
        for star in (6, 5, 4, 3):
            pools.extend(combined_operator_pool(star))
    else:
        pools.extend(combined_operator_pool(rarity))

    for operator in pools:
        if operator_matches_name(operator, name):
            return dict(operator)
    return None


def choose_up_operator(names: tuple[str, ...], rarity: int) -> dict[str, Any] | None:
    candidates = [item for name in names if (item := find_operator_by_name(name, rarity=rarity))]
    if not candidates:
        return None
    return dict(random.choice(candidates))


def banner_catalog_entries() -> list[dict[str, Any]]:
    entries = sorted(
        catalog_up_banner_records(),
        key=lambda item: int(item.get("open_time") or 0),
        reverse=True,
    )
    if entries:
        return entries

    fallback: list[dict[str, Any]] = []
    for key in ("standard", "limited"):
        data = banner_config(key)
        fallback.append(
            {
                "key": key,
                "title": str(data.get("title") or key),
                "description": str(data.get("description") or ""),
                "open_date": "",
                "up_6": list(data.get("six_up") or ()),
                "builtin": True,
            }
        )
    return fallback


def banner_catalog_keys() -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for item in banner_catalog_entries():
        key = str(item.get("key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def store_banner_catalog(
    state: dict[str, Any],
    keys: list[str],
    page: int = 1,
    source: str = "directory",
) -> None:
    state["banner_catalog"] = {
        "keys": keys,
        "page": int(page or 1),
        "source": source,
        "updated_at": int(time.time()),
    }


def active_banner_catalog_keys(state: dict[str, Any]) -> list[str]:
    catalog = state.get("banner_catalog")
    if not isinstance(catalog, dict):
        return []
    updated_at = int(catalog.get("updated_at") or 0)
    if updated_at and time.time() - updated_at > BANNER_CATALOG_TTL_SECONDS:
        return []
    keys = catalog.get("keys")
    if not isinstance(keys, list):
        return []
    return [str(key) for key in keys if str(key or "")]


def current_banner_catalog_page(state: dict[str, Any]) -> int:
    catalog = state.get("banner_catalog")
    if isinstance(catalog, dict):
        return int(catalog.get("page") or 1)
    return 1


def banner_catalog_page_count(per_page: int = 15) -> int:
    return max(1, (len(banner_catalog_entries()) + per_page - 1) // per_page)


def clamp_banner_catalog_page(page: int, per_page: int = 15) -> int:
    return max(1, min(int(page or 1), banner_catalog_page_count(per_page=per_page)))


def format_catalog_entry(index: int, item: dict[str, Any], selected_banner: str) -> str:
    key = str(item.get("key") or "")
    marker = "（当前）" if key == selected_banner else ""
    title = str(item.get("title") or key)
    open_date = str(item.get("open_date") or "")
    prefix = f"{open_date} " if open_date else ""
    up6 = " / ".join(str(name) for name in (item.get("up_6") or [])[:4])
    detail = up6 or str(item.get("description") or "")
    if detail:
        return f"{index}. {prefix}{title}{marker}：{detail}"
    return f"{index}. {prefix}{title}{marker}"


def banner_list_text(selected_banner: str, page: int = 1, per_page: int = 15) -> str:
    entries = banner_catalog_entries()
    total = len(entries)
    page = clamp_banner_catalog_page(page, per_page=per_page)
    page_count = banner_catalog_page_count(per_page=per_page)
    start = (page - 1) * per_page
    shown = entries[start : start + per_page]

    lines = [f"方舟UP/限定池目录（第 {page}/{page_count} 页，共 {total} 个）", "━━━━━━"]
    for offset, item in enumerate(shown, start + 1):
        lines.append(format_catalog_entry(offset, item, selected_banner))

    lines.append("━━━━━━")
    lines.append("想切换就回复：温德尔 4（数字换成上面的编号）。")
    if page_count > 1:
        lines.append("翻页：方舟卡池 第2页 / 方舟卡池 下一页 / 方舟卡池 上一页。")
    lines.append("已隐藏中坚、联合、定向、归航和普池编号。")
    lines.append("也可以直接搜：方舟卡池 水月 / 方舟卡池 巨斧与笔尖 / 方舟卡池 最新。")
    return "\n".join(lines)


def banner_matches_text(matches: list[dict[str, Any]], query: str) -> str:
    if not matches:
        return f"没找到和“{query.strip()}”匹配的方舟UP池。可以试试：方舟卡池 水月 / 方舟卡池 最新。"
    lines = [f"找到 {len(matches)} 个可能的方舟UP池：", "━━━━━━"]
    for index, item in enumerate(matches[:12], 1):
        six_up = " / ".join(str(name) for name in (item.get("up_6") or [])[:5]) or "无六星UP"
        lines.append(f"{index}. {item.get('open_date') or '?'} {item.get('title')}：{six_up}")
    lines.append("想切换就回复：温德尔 1（数字换成上面的编号），也可以发方舟卡池 + 池名或UP干员名。")
    return "\n".join(lines)


def select_banner_response(state: dict[str, Any], banner_key: str) -> str:
    state["selected_banner"] = banner_key
    banner = banner_config(banner_key)
    up6 = " / ".join(str(name) for name in tuple(banner.get("six_up") or ())[:6]) or "无六星UP"
    up5 = " / ".join(str(name) for name in tuple(banner.get("five_up") or ())[:6]) or "无五星UP"
    source = "历史UP池" if banner.get("legacy") else ("官方UP池" if banner.get("official") else "模拟池")
    return (
        f"已切换到 {banner_title(banner_key)}。\n"
        f"{source}；6★UP：{up6}\n"
        f"5★UP：{up5}\n"
        "下次不写卡池时，就默认抽这个池。"
    )


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
        "banner_catalog": {},
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
    state.setdefault("banner_catalog", {})
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
        if banner.get("official") and len(tuple(banner.get("six_up") or ())) >= 3:
            up_chance = 0.7 if banner.get("limited") else 0.6
        if up and random.random() < up_chance:
            return up
        if banner.get("limited") and LIMITED_POOL and random.random() < 0.35:
            return dict(random.choice(LIMITED_POOL))
    if rarity == 5:
        up = choose_up_operator(tuple(banner.get("five_up") or ()), rarity=5)
        if up and random.random() < 0.5:
            return up
    if rarity == 4:
        up = choose_up_operator(tuple(banner.get("four_up") or ()), rarity=4)
        if up and random.random() < 0.2:
            return up
    return dict(random.choice(combined_operator_pool(rarity)))


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


def safe_cache_name(name: str) -> str:
    digest = hashlib.sha1(str(name or "").encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "").strip())[:18].strip("_")
    return f"{slug or 'operator'}_{digest}"


def load_prts_half_map() -> dict[str, str]:
    if PRTS_HALF_MAP_PATH.exists():
        try:
            data = json.loads(PRTS_HALF_MAP_PATH.read_text(encoding="utf-8"))
            fetched_at = float(data.get("fetched_at") or 0)
            halves = data.get("halves")
            if isinstance(halves, dict) and halves and time.time() - fetched_at < 7 * 24 * 3600:
                return {str(k): str(v) for k, v in halves.items() if v}
        except Exception:
            pass

    try:
        text = fetch_url_bytes(PRTS_OPERATOR_LIST_URL, timeout=20).decode("utf-8", errors="replace")
        halves: dict[str, str] = {}
        for tag in re.findall(r"<div[^>]+class=[\"']smwdata[\"'][^>]*>", text):
            attrs = {
                key: html.unescape(value)
                for key, value in re.findall(r"([\w:-]+)=[\"'](.*?)[\"']", tag)
            }
            name = attrs.get("data-cn", "").strip()
            half = attrs.get("data-half", "").strip()
            if not name or not half:
                continue
            if half.startswith("//"):
                half = "https:" + half
            elif half.startswith("/"):
                half = urljoin("https://prts.wiki", half)
            halves[name] = half
        if halves:
            PRTS_HALF_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
            PRTS_HALF_MAP_PATH.write_text(
                json.dumps({"fetched_at": time.time(), "halves": halves}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return halves
    except Exception:
        pass

    if PRTS_HALF_MAP_PATH.exists():
        try:
            data = json.loads(PRTS_HALF_MAP_PATH.read_text(encoding="utf-8"))
            halves = data.get("halves")
            if isinstance(halves, dict):
                return {str(k): str(v) for k, v in halves.items() if v}
        except Exception:
            pass
    return {}


def fetch_url_bytes(url: str, timeout: int = 20) -> bytes:
    try:
        import requests

        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Wendell QQ bot)"},
            timeout=timeout,
        )
        response.raise_for_status()
        return bytes(response.content)
    except ModuleNotFoundError:
        from urllib.request import Request, urlopen

        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (Wendell QQ bot)"})
        with urlopen(request, timeout=timeout) as response:
            return response.read()


def resolve_prts_file_image_url(file_name: str) -> str:
    page_url = "https://prts.wiki/w/" + quote(f"文件:{file_name}")
    text = fetch_url_bytes(page_url, timeout=12).decode("utf-8", errors="replace")
    patterns = (
        r'<div[^>]+class=["\']fullImageLink["\'][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\']',
        r'<div[^>]+id=["\']file["\'][^>]*>\s*<a[^>]+href=["\']([^"\']+)["\']',
        r'<a[^>]+href=["\'](https://media\.prts\.wiki/[^"\']+?\.png)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return html.unescape(match.group(1)).split("?", 1)[0]
    return ""


def resolve_operator_portrait_url(name: str) -> str:
    halves = load_prts_half_map()
    url = halves.get(name)
    if url:
        return url

    compact = re.sub(r"\s+", "", name)
    for candidate_name, candidate_url in halves.items():
        if compact and compact == re.sub(r"\s+", "", candidate_name):
            return candidate_url

    for file_name in (
        f"半身像_{name}_1.png",
        f"半身像_{name}.png",
        f"立绘_{name}_1.png",
    ):
        try:
            url = resolve_prts_file_image_url(file_name)
            if url:
                return url
        except Exception:
            continue
    return ""


def ensure_operator_portrait(name: str) -> Path | None:
    value = str(name or "").strip()
    if not value:
        return None
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    target = PORTRAIT_DIR / f"{safe_cache_name(value)}.png"
    if target.exists() and target.stat().st_size > 0:
        return target

    url = resolve_operator_portrait_url(value)
    if not url:
        return None

    try:
        from PIL import Image

        target.write_bytes(fetch_url_bytes(url, timeout=20))
        with Image.open(target) as image:
            image.convert("RGBA").save(target)
        return target
    except Exception:
        try:
            if target.exists():
                target.unlink()
        except Exception:
            pass
        return None


def load_akgacha_background(rarity: int, size: tuple[int, int]):
    from PIL import Image, ImageDraw

    path = ASSET_DIR / f"back_{max(3, min(6, int(rarity)))}.png"
    if path.exists():
        return Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)

    light, dark = rarity_colors(rarity)
    fallback = Image.new("RGBA", size, (*dark, 255))
    draw = ImageDraw.Draw(fallback, "RGBA")
    draw.rectangle((0, 0, size[0], 18), fill=(*light, 255))
    return fallback


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
    from PIL import Image, ImageDraw, ImageFilter

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    visible = list(results)
    if len(results) > 10:
        rare = [item for item in results if int(item.get("rarity") or 0) >= 5 or item.get("limited")]
        visible = rare[:30] if rare else results[:10]

    card_w = 132
    card_h = 276
    gap = 8
    padding = 36
    header_h = 92
    footer_h = 64
    cols = min(10, max(1, len(visible)))
    if len(visible) <= 5:
        cols = len(visible)
    rows = max(1, (len(visible) + cols - 1) // cols)
    width = max(920, padding * 2 + cols * card_w + max(0, cols - 1) * gap)
    height = padding + header_h + rows * card_h + max(0, rows - 1) * gap + footer_h + padding
    image = Image.new("RGB", (width, height), (25, 27, 31))
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(height):
        blend = y / max(1, height - 1)
        color = (
            int(20 + 20 * blend),
            int(23 + 18 * blend),
            int(30 + 20 * blend),
        )
        draw.line((0, y, width, y), fill=color)

    for x in range(-height, width, 46):
        draw.line((x, 0, x + height, height), fill=(255, 255, 255, 10), width=1)

    title_font = load_font(38, True)
    subtitle_font = load_font(21)
    small_font = load_font(17)
    badge_font = load_font(18, True)

    title = f"{banner_title(banner_key)} · {len(results)} 抽"
    draw.text((padding, padding + 2), title, fill=(255, 255, 255), font=title_font)
    now = datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M")
    draw.text((padding, padding + 51), f"{nickname or '博士'} · {now}", fill=(174, 184, 195), font=subtitle_font)

    counts = {rarity: sum(1 for result in results if int(result["rarity"]) == rarity) for rarity in (6, 5, 4, 3)}
    badges = [
        f"6★ {counts[6]}",
        f"5★ {counts[5]}",
        f"4★ {counts[4]}",
        f"3★ {counts[3]}",
        f"保底 {int(state.get('pity') or 0)}",
    ]
    x = width - padding
    y = padding + 13
    for badge in badges:
        tw, th = text_size(draw, badge, badge_font)
        x -= tw + 28
        draw.rounded_rectangle((x, y, x + tw + 26, y + 34), radius=3, fill=(42, 45, 52), outline=(96, 101, 113))
        draw.text((x + 13, y + 6), badge, fill=(248, 219, 92), font=badge_font)
        x -= 8

    start_y = padding + header_h
    row_width = cols * card_w + max(0, cols - 1) * gap
    start_x = (width - row_width) // 2
    for index, result in enumerate(visible):
        row = index // cols
        col = index % cols
        x1 = start_x + col * (card_w + gap)
        y1 = start_y + row * (card_h + gap)
        rarity = int(result.get("rarity") or 3)
        card = load_akgacha_background(rarity, (card_w, card_h))

        portrait_path = ensure_operator_portrait(str(result.get("name") or ""))
        if portrait_path:
            try:
                face = Image.open(portrait_path).convert("RGBA").resize((card_w, card_h), Image.Resampling.LANCZOS)
                shadow = face.filter(ImageFilter.GaussianBlur(radius=4))
                card.alpha_composite(shadow, (3, 4))
                card.alpha_composite(face, (0, 0))
            except Exception:
                portrait_path = None

        if not portrait_path:
            card_draw = ImageDraw.Draw(card, "RGBA")
            card_draw.rectangle((0, 0, card_w, card_h), fill=(0, 0, 0, 10))
            card_draw.line((16, 62, card_w - 16, 62), fill=(255, 255, 255, 46), width=2)
            card_draw.line((16, 72, card_w - 38, 72), fill=(255, 255, 255, 28), width=1)

        image.paste(card, (x1, y1), card)
        draw.rectangle((x1, y1 + card_h - 68, x1 + card_w, y1 + card_h), fill=(0, 0, 0, 150))
        star_text_value = "★" * rarity
        draw.text((x1 + 8, y1 + card_h - 62), star_text_value, fill=(255, 232, 122), font=load_font(16, True))
        name = fit_text(draw, str(result.get("name") or "未知"), load_font(20, True), card_w - 16)
        profession = fit_text(draw, str(result.get("profession") or ""), load_font(14), card_w - 16)
        draw.text((x1 + 8, y1 + card_h - 40), name, fill=(255, 255, 255), font=load_font(20, True))
        draw.text((x1 + 8, y1 + card_h - 17), profession, fill=(206, 214, 222), font=load_font(14))
        if result.get("limited"):
            draw.rectangle((x1 + card_w - 45, y1 + 8, x1 + card_w - 8, y1 + 31), fill=(225, 64, 83))
            draw.text((x1 + card_w - 41, y1 + 10), "限定", fill=(255, 255, 255), font=load_font(13, True))

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


def parse_banner_selection_number(text: str) -> int | None:
    compact = re.sub(r"\s+", "", str(text or "").strip().lower())
    if not compact:
        return None
    match = re.fullmatch(r"(?:方舟|明日方舟)?(?:卡池|池子)?(?:编号|第)?(\d{1,3})(?:号|个)?", compact)
    if not match:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def parse_banner_page_request(compact: str) -> int | str | None:
    if "下一页" in compact or "下页" in compact:
        return "next"
    if "上一页" in compact or "上页" in compact:
        return "prev"
    match = re.search(r"(?:第)?(\d{1,3})(?:页|p)", compact)
    if match:
        return int(match.group(1))
    return None


def parse_command(text: str) -> dict[str, Any] | None:
    value = text.strip()
    compact = re.sub(r"\s+", "", value.lower())
    if not any(mark in compact for mark in ("方舟", "明日方舟", "arknights")):
        return None

    banner_key = resolve_banner_key_from_text(compact)
    if "卡池" in compact or "池子" in compact:
        page = parse_banner_page_request(compact)
        if page is not None:
            if page == "next":
                return {"action": "banners", "page_delta": 1}
            if page == "prev":
                return {"action": "banners", "page_delta": -1}
            return {"action": "banners", "page": page}
        number = parse_banner_selection_number(value)
        if number:
            return {"action": "select_banner_number", "number": number}
        if banner_key:
            return {"action": "select_banner", "banner": banner_key}
        query = clean_banner_query(value)
        if query:
            return {"action": "banner_search", "query": query}
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


def looks_like_banner_number_reply(text: str, user_key: str) -> bool:
    number = parse_banner_selection_number(text)
    if not number:
        return False
    data = load_state()
    users = data.get("users") if isinstance(data.get("users"), dict) else {}
    state = users.get(user_key) if isinstance(users, dict) else None
    if not isinstance(state, dict):
        return False
    keys = active_banner_catalog_keys(state)
    return 1 <= number <= len(keys)


def handle_command_payload(text: str, user_key: str, nickname: str = "") -> tuple[str, Path | None, str]:
    command = parse_command(text)
    if not command:
        number = parse_banner_selection_number(text)
        if number:
            command = {"action": "select_banner_number", "number": number}
    if not command:
        return "", None, ""

    with STATE_LOCK:
        data = load_state()
        state = get_user_state(data, user_key)

        action = command["action"]
        if action == "help":
            answer = (
                "方舟寻访用法：方舟单抽 / 方舟十连 / 方舟抽卡 50 / 方舟来一井 / "
                "方舟限定十连 / 方舟中坚抽卡50 / 方舟卡池 / 方舟卡池 水月 / 方舟卡池 最新 / 温德尔 1 切换目录编号 / 方舟状态 / 方舟重置"
            )
            return answer, None, answer
        if action == "banners":
            requested_page = command.get("page")
            if requested_page is None and command.get("page_delta"):
                requested_page = current_banner_catalog_page(state) + int(command.get("page_delta") or 0)
            page = clamp_banner_catalog_page(int(requested_page or current_banner_catalog_page(state) or 1))
            keys = banner_catalog_keys()
            store_banner_catalog(state, keys, page=page, source="directory")
            save_state(data)
            answer = banner_list_text(str(state.get("selected_banner") or "standard"), page=page)
            return answer, None, answer
        if action == "banner_search":
            query = str(command.get("query") or "")
            matches = find_official_banner_matches(query, limit=12)
            if len(matches) == 1:
                answer = select_banner_response(state, str(matches[0].get("key") or "standard"))
                save_state(data)
            else:
                store_banner_catalog(
                    state,
                    [str(item.get("key") or "") for item in matches if item.get("key")],
                    page=1,
                    source="search",
                )
                save_state(data)
                answer = banner_matches_text(matches, query)
            return answer, None, answer
        if action == "select_banner_number":
            number = int(command.get("number") or 0)
            keys = active_banner_catalog_keys(state)
            if not keys:
                answer = "这个编号我现在对不上了……先发“方舟卡池”让我重新列一遍目录。"
                return answer, None, answer
            if number < 1 or number > len(keys):
                answer = f"这个编号超出目录了。现在能选 1 到 {len(keys)}，可以发“方舟卡池”重新看。"
                return answer, None, answer
            banner_key = keys[number - 1]
            if banner_key not in BANNERS and banner_key not in official_banners_by_key():
                answer = "这个编号对应的卡池好像失效了……先发“方舟卡池”让我重新列一遍。"
                return answer, None, answer
            answer = select_banner_response(state, banner_key)
            save_state(data)
            return answer, None, answer
        if action == "select_banner":
            banner_key = str(command.get("banner") or "standard")
            if banner_key not in BANNERS and banner_key not in official_banners_by_key():
                answer = "这个卡池我没找到……可以先发“方舟卡池”看看最近可选池。"
                return answer, None, answer
            answer = select_banner_response(state, banner_key)
            save_state(data)
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
        if banner_key not in BANNERS and banner_key not in official_banners_by_key():
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
