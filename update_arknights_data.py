from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "arknights_gacha_official.json"
LEGACY_AKGACHA_CONFIG_PATH = DATA_DIR / "akgacha_legacy_config.json"

GACHA_TABLE_URLS = (
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/gacha_table.json",
    "https://cdn.jsdelivr.net/gh/Kengxxiao/ArknightsGameData@master/zh_CN/gamedata/excel/gacha_table.json",
)
CHARACTER_TABLE_URLS = (
    "https://cdn.jsdelivr.net/gh/Kengxxiao/ArknightsGameData@master/zh_CN/gamedata/excel/character_table.json",
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/character_table.json",
)

PROFESSION_MAP = {
    "PIONEER": "先锋",
    "WARRIOR": "近卫",
    "SNIPER": "狙击",
    "TANK": "重装",
    "MEDIC": "医疗",
    "SUPPORT": "辅助",
    "CASTER": "术师",
    "SPECIAL": "特种",
}


def fetch_json(urls: tuple[str, ...]) -> Any:
    last_error: Exception | None = None
    for url in urls:
        try:
            request = Request(url, headers={"User-Agent": "Wendell QQ bot data updater"})
            with urlopen(request, timeout=90) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"failed to fetch data: {last_error}")


def strip_tags(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"<@[^>]+>|</>", "", text)
    text = text.replace("\\n", "\n")
    return text


def split_names(value: str) -> list[str]:
    text = re.sub(r"（.*?）|\(.*?\)", "", str(value or ""))
    text = text.replace("、", "/").replace("，", "/")
    return [item.strip() for item in re.split(r"\s*/\s*|／", text) if item.strip()]


def parse_up_from_detail(detail: str) -> dict[str, list[str]]:
    text = strip_tags(detail)
    marker = "※出现率上升※"
    if marker not in text:
        return {"6": [], "5": [], "4": []}

    part = text.split(marker, 1)[1]
    end_marker = "※全部可能出现的干员※"
    if end_marker in part:
        part = part.split(end_marker, 1)[0]

    result: dict[str, list[str]] = {"6": [], "5": [], "4": []}
    for rarity, stars in (("6", "★★★★★★"), ("5", "★★★★★"), ("4", "★★★★")):
        match = re.search(re.escape(stars) + r"\s*\n\s*([^\n★※]+)", part)
        if match:
            result[rarity] = split_names(match.group(1))
    return result


def build_char_maps(character_table: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for char_id, raw in character_table.items():
        if not isinstance(raw, dict) or not str(char_id).startswith("char_"):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        rarity_raw = raw.get("rarity")
        if isinstance(rarity_raw, str) and rarity_raw.startswith("TIER_"):
            rarity = int(rarity_raw.removeprefix("TIER_")) + 1
        else:
            rarity = int(rarity_raw or 0) + 1
        operator = {
            "id": char_id,
            "name": name,
            "rarity": rarity,
            "profession": PROFESSION_MAP.get(str(raw.get("profession") or ""), "干员"),
            "obtain": str(raw.get("itemObtainApproach") or ""),
        }
        by_id[char_id] = operator
        by_name[name] = operator
    return by_id, by_name


def names_from_ids(ids: Any, by_id: dict[str, dict[str, Any]]) -> list[str]:
    if not isinstance(ids, list):
        ids = [ids] if ids else []
    result: list[str] = []
    for char_id in ids:
        operator = by_id.get(str(char_id))
        if operator:
            result.append(operator["name"])
    return result


def dynmeta_up(pool: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    meta = pool.get("dynMeta")
    result: dict[str, list[str]] = {"6": [], "5": [], "4": []}
    if not isinstance(meta, dict):
        return result

    if "main6RarityCharId" in meta:
        result["6"].extend(names_from_ids(meta.get("main6RarityCharId"), by_id))
    if "sub6RarityCharId" in meta:
        result["6"].extend(names_from_ids(meta.get("sub6RarityCharId"), by_id))
    if "rare5CharList" in meta:
        result["5"].extend(names_from_ids(meta.get("rare5CharList"), by_id))

    pick = meta.get("rarityPickCharDict")
    if isinstance(pick, dict):
        result["6"].extend(names_from_ids(pick.get("TIER_6"), by_id))
        result["5"].extend(names_from_ids(pick.get("TIER_5"), by_id))

    for rarity in result:
        seen: set[str] = set()
        result[rarity] = [name for name in result[rarity] if not (name in seen or seen.add(name))]
    return result


def title_for_pool(pool: dict[str, Any], up: dict[str, list[str]]) -> str:
    name = str(pool.get("gachaPoolName") or "未命名卡池").strip()
    pool_id = str(pool.get("gachaPoolId") or "")
    if name in {"适合多种场合的强力干员", "定向甄选"}:
        if up.get("6"):
            name = f"{name}（{' / '.join(up['6'][:3])}）"
        elif up.get("5"):
            name = f"{name}（{' / '.join(up['5'][:3])}）"
    if not name:
        name = pool_id
    return name


def build_data() -> dict[str, Any]:
    gacha_table = fetch_json(GACHA_TABLE_URLS)
    character_table = fetch_json(CHARACTER_TABLE_URLS)
    by_id, by_name = build_char_maps(character_table)

    operators = [
        {
            "name": operator["name"],
            "rarity": operator["rarity"],
            "profession": operator["profession"],
        }
        for operator in by_name.values()
        if 3 <= int(operator["rarity"]) <= 6 and operator["obtain"]
    ]
    operators.sort(key=lambda item: (item["rarity"], item["name"]))

    banners: list[dict[str, Any]] = []
    for pool in gacha_table.get("gachaPoolClient", []):
        if not isinstance(pool, dict):
            continue
        up = dynmeta_up(pool, by_id)
        detail_up = parse_up_from_detail(str(pool.get("gachaPoolDetail") or ""))
        for rarity in ("6", "5", "4"):
            if not up[rarity]:
                up[rarity] = detail_up[rarity]
        if not any(up.values()):
            continue

        pool_id = str(pool.get("gachaPoolId") or "")
        rule_type = str(pool.get("gachaRuleType") or "")
        open_time = int(pool.get("openTime") or 0)
        end_time = int(pool.get("endTime") or 0)
        limited = rule_type in {"LIMITED", "LINKAGE"} or "限定" in str(pool.get("gachaPoolName") or "")
        banners.append(
            {
                "key": pool_id,
                "title": title_for_pool(pool, up),
                "pool_id": pool_id,
                "rule_type": rule_type,
                "limited": limited,
                "open_time": open_time,
                "end_time": end_time,
                "open_date": datetime.fromtimestamp(open_time).strftime("%Y-%m-%d") if open_time else "",
                "end_date": datetime.fromtimestamp(end_time).strftime("%Y-%m-%d") if end_time else "",
                "up_6": up["6"],
                "up_5": up["5"],
                "up_4": up["4"],
            }
        )

    banners.sort(key=lambda item: (int(item.get("open_time") or 0), str(item.get("pool_id") or "")))
    merge_legacy_akgacha_banners(banners)
    banners.sort(key=lambda item: (int(item.get("open_time") or 0), str(item.get("pool_id") or "")))
    return {
        "source": "Kengxxiao/ArknightsGameData zh_CN gacha_table.json + character_table.json",
        "source_url": "https://github.com/Kengxxiao/ArknightsGameData",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "banner_count": len(banners),
        "operators": operators,
        "banners": banners,
    }


def merge_legacy_akgacha_banners(banners: list[dict[str, Any]]) -> None:
    if not LEGACY_AKGACHA_CONFIG_PATH.exists():
        return
    try:
        legacy = json.loads(LEGACY_AKGACHA_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return

    existing_signatures = {
        (
            tuple(item.get("up_6") or ()),
            tuple(item.get("up_5") or ()),
            tuple(item.get("up_4") or ()),
            int(item.get("open_time") or 0),
        )
        for item in banners
    }
    existing_keys = {str(item.get("key") or "") for item in banners}
    for name, raw in (legacy.get("banners") or {}).items():
        if not isinstance(raw, dict):
            continue
        up_6 = [str(item) for item in raw.get("up_6") or []]
        up_5 = [str(item) for item in raw.get("up_5") or []]
        up_4 = [str(item) for item in raw.get("up_4") or []]
        if not (up_6 or up_5 or up_4):
            continue
        open_time = int(float(raw.get("open") or 0))
        signature = (tuple(up_6), tuple(up_5), tuple(up_4), open_time)
        if signature in existing_signatures:
            continue
        slug = re.sub(r"\W+", "_", str(name))
        key = f"legacy_{open_time}_{slug}"
        if key in existing_keys:
            continue
        banners.append(
            {
                "key": key,
                "title": str(name),
                "pool_id": key,
                "rule_type": "LEGACY_LIMITED" if raw.get("limited") else "LEGACY",
                "limited": bool(raw.get("limited")),
                "open_time": open_time,
                "end_time": int(float(raw.get("end") or 0)),
                "open_date": datetime.fromtimestamp(open_time).strftime("%Y-%m-%d") if open_time else "",
                "end_date": datetime.fromtimestamp(int(float(raw.get("end") or 0))).strftime("%Y-%m-%d")
                if raw.get("end")
                else "",
                "up_6": up_6,
                "up_5": up_5,
                "up_4": up_4,
            }
        )
        existing_signatures.add(signature)
        existing_keys.add(key)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = build_data()
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {data['banner_count']} banners and {len(data['operators'])} operators.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
