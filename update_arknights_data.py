from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "arknights_gacha_official.json"
LEGACY_AKGACHA_CONFIG_PATH = DATA_DIR / "akgacha_legacy_config.json"
CHINA_TZ = ZoneInfo("Asia/Shanghai")

GACHA_TABLE_URLS = (
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/gacha_table.json",
    "https://cdn.jsdelivr.net/gh/Kengxxiao/ArknightsGameData@master/zh_CN/gamedata/excel/gacha_table.json",
)
CHARACTER_TABLE_URLS = (
    "https://cdn.jsdelivr.net/gh/Kengxxiao/ArknightsGameData@master/zh_CN/gamedata/excel/character_table.json",
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/excel/character_table.json",
)
PRTS_LIMITED_PAGE_TITLE = "卡池一览/限时寻访"

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


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Wendell QQ bot data updater"})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "ignore")


def strip_tags(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"<@[^>]+>|</>", "", text)
    text = text.replace("\\n", "\n")
    return text


def china_timestamp(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return int(parsed.replace(tzinfo=CHINA_TZ).timestamp())
        except ValueError:
            continue
    return 0


def clean_operator_name(name: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(name or ""))
    text = re.sub(r"\{\{.*?\}\}", "", text)
    text = text.replace("（占6）", "").replace(" （占6）", "").replace("(占6)", "")
    return text.strip()


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


def fetch_prts_limited_wikitext() -> str:
    title = quote(PRTS_LIMITED_PAGE_TITLE)
    return fetch_text(f"https://prts.wiki/index.php?title={title}&action=raw")


def split_wiki_table_rows(wikitext: str) -> list[list[str]]:
    if "==非标准寻访==" not in wikitext:
        return []
    section = wikitext.split("==非标准寻访==", 1)[1]
    if "==标准寻访==" in section:
        section = section.split("==标准寻访==", 1)[0]

    rows: list[list[str]] = []
    cells: list[str] = []
    current_cell: list[str] = []
    table_depth = 0

    def finish_cell() -> None:
        nonlocal current_cell
        if current_cell:
            cells.append("\n".join(current_cell).strip())
            current_cell = []

    def finish_row() -> None:
        nonlocal cells
        finish_cell()
        if len(cells) >= 4:
            rows.append(cells[:4])
        cells = []

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("{|"):
            if table_depth > 0 and current_cell:
                current_cell.append(line)
            table_depth += 1
            continue

        if line.startswith("|}"):
            if table_depth > 1 and current_cell:
                current_cell.append(line)
            table_depth = max(0, table_depth - 1)
            if table_depth == 0:
                finish_row()
            continue

        if table_depth == 1 and line == "|-":
            finish_row()
            continue

        if table_depth == 1 and line.startswith("|") and not line.startswith("|-"):
            finish_cell()
            current_cell = [line[1:].strip()]
            continue

        if table_depth >= 1 and current_cell:
            current_cell.append(line)

    finish_row()
    return rows


def prts_banner_title(cell: str) -> str:
    links = re.findall(r"\[\[(?!文件:)(?:[^\]|]+\|)?([^\]]+)\]\]", cell)
    if links:
        return links[-1].strip()
    text = re.sub(r"\[\[文件:[^\]]+\]\]", "", cell)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    return text.strip()


def prts_banner_times(cell: str) -> tuple[int, int, str, str]:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?", cell)
    start = dates[0] if dates else ""
    end = dates[1] if len(dates) > 1 else ""
    return (
        china_timestamp(start),
        china_timestamp(end),
        start[:10],
        end[:10],
    )


def prts_operator_names(cell: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"\{\{干员头像\|([^}|]+)", cell):
        name = clean_operator_name(match.group(1))
        if name and name not in names:
            names.append(name)
    return names


def split_prts_five_four_names(names: list[str], by_name: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    up5: list[str] = []
    up4: list[str] = []
    for name in names:
        rarity = int((by_name.get(name) or {}).get("rarity") or 5)
        target = up4 if rarity == 4 else up5
        if name not in target:
            target.append(name)
    return up5, up4


def merge_prts_limited_banners(banners: list[dict[str, Any]], by_name: dict[str, dict[str, Any]]) -> None:
    try:
        wikitext = fetch_prts_limited_wikitext()
    except Exception as exc:
        print(f"Skipped PRTS limited banner import: {exc}")
        return

    existing = {
        (str(item.get("open_date") or ""), str(item.get("title") or ""))
        for item in banners
    }
    existing_keys = {str(item.get("key") or "") for item in banners}
    for cells in split_wiki_table_rows(wikitext):
        title = prts_banner_title(cells[0])
        if not title:
            continue
        open_time, end_time, open_date, end_date = prts_banner_times(cells[1])
        if (open_date, title) in existing:
            continue
        up6 = prts_operator_names(cells[2])
        up5, up4 = split_prts_five_four_names(prts_operator_names(cells[3]), by_name)
        if not (up6 or up5 or up4):
            continue
        slug = re.sub(r"\W+", "_", title).strip("_") or "banner"
        key = f"prts_{open_time}_{slug}"
        if key in existing_keys:
            continue
        limited = "限定干员" in cells[2] or "限定干员" in cells[3]
        banners.append(
            {
                "key": key,
                "title": title,
                "pool_id": key,
                "rule_type": "PRTS_LIMITED" if limited else "PRTS_UP",
                "limited": limited,
                "open_time": open_time,
                "end_time": end_time,
                "open_date": open_date,
                "end_date": end_date,
                "up_6": up6,
                "up_5": up5,
                "up_4": up4,
                "source": "PRTS 卡池一览/限时寻访",
            }
        )
        existing.add((open_date, title))
        existing_keys.add(key)


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
    merge_prts_limited_banners(banners, by_name)
    banners.sort(key=lambda item: (int(item.get("open_time") or 0), str(item.get("pool_id") or "")))
    merge_legacy_akgacha_banners(banners)
    banners.sort(key=lambda item: (int(item.get("open_time") or 0), str(item.get("pool_id") or "")))
    return {
        "source": "Kengxxiao/ArknightsGameData zh_CN + PRTS 卡池一览/限时寻访 + legacy akgacha config",
        "source_url": "https://github.com/Kengxxiao/ArknightsGameData ; https://prts.wiki/w/卡池一览/限时寻访",
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
