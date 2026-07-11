from __future__ import annotations

import json
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache" / "steam_status"
STATE_PATH = BASE_DIR / "bot_memory" / "steam_status.json"
STATUS_IMAGE_PATH = BASE_DIR / "steam_status.jpg"
STATUS_OVERVIEW_IMAGE_PATH = BASE_DIR / "steam_status_overview.jpg"
RANK_IMAGE_PATH = BASE_DIR / "steam_playtime_rank.jpg"

PLAYER_SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
FRIEND_LIST_URL = "https://api.steampowered.com/ISteamUser/GetFriendList/v0001/"
OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
APP_HEADER_URLS = (
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
    "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

WIDTH = 980
PADDING = 42
BG_TOP = (14, 23, 39)
BG_BOTTOM = (7, 10, 20)
PANEL = (24, 37, 58)
PANEL_2 = (30, 48, 75)
LINE = (75, 101, 139)
TEXT = (242, 248, 255)
MUTED = (174, 190, 210)
GREEN = (102, 239, 155)
BLUE = (91, 169, 255)
YELLOW = (255, 213, 86)


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
FONT_SUBTITLE = load_font(22)
FONT_SECTION = load_font(30, True)
FONT_CARD_TITLE = load_font(27, True)
FONT_CARD_TEXT = load_font(20)
FONT_SMALL = load_font(16)
FONT_BADGE = load_font(18, True)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
    return session


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
    if lines:
        lines[-1] = fit_text(draw, lines[-1], font, max_width)
    return lines[:max_lines]


def gradient_background(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), BG_TOP)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(BG_TOP[i] * (1 - ratio) + BG_BOTTOM[i] * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=color)
    return image


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def paste_rounded(base: Image.Image, image: Image.Image, box: tuple[int, int], size: tuple[int, int], radius: int) -> None:
    fitted = ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    base.paste(fitted, box, rounded_mask(size, radius))


def steam_id_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{15,20}", text) else ""


def list_config(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def config_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enable", "enabled"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disable", "disabled"}:
            return False
    return default


def configured_player_ids(config: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in list_config(config.get("steam_players")):
        steam_id = steam_id_text(item.get("steam_id") if isinstance(item, dict) else item)
        if steam_id and steam_id not in ids:
            ids.append(steam_id)
    for item in list_config(config.get("steam_player_ids")):
        steam_id = steam_id_text(item)
        if steam_id and steam_id not in ids:
            ids.append(steam_id)
    return ids


def configured_player_aliases(config: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in list_config(config.get("steam_players")):
        if not isinstance(item, dict):
            continue
        steam_id = steam_id_text(item.get("steam_id"))
        alias = str(item.get("name") or item.get("label") or "").strip()
        if steam_id and alias:
            aliases[steam_id] = alias[:40]
    return aliases


def api_key(config: dict[str, Any]) -> str:
    return str(config.get("steam_api_key") or "").strip()


def require_api_key(config: dict[str, Any]) -> str:
    key = api_key(config)
    if not key:
        raise ValueError("Steam Web API key has not been configured.")
    return key


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"players": {}, "playtime_snapshots": {}, "rank": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"players": {}, "playtime_snapshots": {}, "rank": {}}
    if not isinstance(data, dict):
        return {"players": {}, "playtime_snapshots": {}, "rank": {}}
    data.setdefault("players", {})
    data.setdefault("playtime_snapshots", {})
    data.setdefault("rank", {})
    return data


def save_state(data: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def fetch_friend_ids(session: requests.Session, key: str, steam_id: str) -> list[str]:
    response = session.get(
        FRIEND_LIST_URL,
        params={"key": key, "steamid": steam_id, "relationship": "friend"},
        timeout=20,
    )
    response.raise_for_status()
    friends = response.json().get("friendslist", {}).get("friends", [])
    ids: list[str] = []
    if isinstance(friends, list):
        for item in friends:
            if not isinstance(item, dict):
                continue
            friend_id = steam_id_text(item.get("steamid"))
            if friend_id and friend_id not in ids:
                ids.append(friend_id)
    return ids


def monitored_steam_ids(config: dict[str, Any], session: requests.Session | None = None) -> list[str]:
    ids = configured_player_ids(config)
    sources = [steam_id_text(item) for item in list_config(config.get("steam_friend_source_steam_ids"))]
    sources = [item for item in sources if item]
    if sources:
        key = require_api_key(config)
        session = session or make_session()
        limit = max(0, min(int(config.get("steam_friend_limit") or 50), 200))
        for source in sources:
            try:
                for friend_id in fetch_friend_ids(session, key, source)[:limit]:
                    if friend_id not in ids:
                        ids.append(friend_id)
            except Exception as exc:
                print(f"Steam friend list fetch failed for {source}: {exc}")
    max_players = max(1, min(int(config.get("steam_max_players") or 50), 100))
    return ids[:max_players]


def fetch_player_summaries(session: requests.Session, key: str, steam_ids: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index in range(0, len(steam_ids), 100):
        chunk = steam_ids[index : index + 100]
        if not chunk:
            continue
        response = session.get(
            PLAYER_SUMMARIES_URL,
            params={"key": key, "steamids": ",".join(chunk)},
            timeout=20,
        )
        response.raise_for_status()
        players = response.json().get("response", {}).get("players", [])
        if not isinstance(players, list):
            continue
        for player in players:
            if not isinstance(player, dict):
                continue
            steam_id = steam_id_text(player.get("steamid"))
            if steam_id:
                result[steam_id] = player
    return result


def fetch_owned_games(session: requests.Session, key: str, steam_id: str) -> list[dict[str, Any]]:
    response = session.get(
        OWNED_GAMES_URL,
        params={
            "key": key,
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        },
        timeout=25,
    )
    response.raise_for_status()
    games = response.json().get("response", {}).get("games", [])
    return games if isinstance(games, list) else []


def cache_path_for_url(url: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", url)[-120:]
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    return CACHE_DIR / f"{safe}{ext}"


def image_from_url(session: requests.Session, url: str, timeout: int = 20) -> Image.Image | None:
    if not url:
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path_for_url(url)
    if path.exists() and path.stat().st_size > 0:
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            pass
    response = session.get(url, timeout=timeout)
    if response.status_code >= 400:
        return None
    data = response.content
    if not data:
        return None
    path.write_bytes(data)
    return Image.open(BytesIO(data)).convert("RGB")


def fetch_app_header(session: requests.Session, appid: str | int) -> Image.Image | None:
    appid_text = str(appid or "").strip()
    if not appid_text:
        return None
    for template in APP_HEADER_URLS:
        try:
            image = image_from_url(session, template.format(appid=appid_text))
            if image:
                return image
        except Exception:
            continue
    return None


def placeholder_image(width: int, height: int, title: str = "Steam") -> Image.Image:
    image = Image.new("RGB", (width, height), PANEL_2)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill=PANEL_2)
    draw.text((width // 2, height // 2 - 20), fit_text(draw, title, FONT_SECTION, width - 80), fill=MUTED, font=FONT_SECTION, anchor="mm")
    return image


def display_name(player: dict[str, Any], aliases: dict[str, str]) -> str:
    steam_id = steam_id_text(player.get("steamid"))
    return aliases.get(steam_id) or str(player.get("personaname") or steam_id or "Steam 玩家").strip()


def format_minutes(minutes: int) -> str:
    minutes = max(0, int(minutes or 0))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}小时{mins}分"
    if hours:
        return f"{hours}小时"
    return f"{mins}分钟"


def draw_badge(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fill: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=12, fill=fill)
    draw.text((box[0] + 14, box[1] + 6), text, fill=(8, 14, 24), font=FONT_BADGE)


def persona_state_text(value: Any) -> str:
    states = {
        0: "离线",
        1: "在线",
        2: "忙碌",
        3: "离开",
        4: "暂离",
        5: "想交易",
        6: "想一起玩",
    }
    try:
        return states.get(int(value or 0), "未知")
    except (TypeError, ValueError):
        return "未知"


def status_overview_rows(config: dict[str, Any], session: requests.Session | None = None) -> list[dict[str, Any]]:
    key = require_api_key(config)
    session = session or make_session()
    steam_ids = monitored_steam_ids(config, session=session)
    if not steam_ids:
        raise ValueError("还没配置 SteamID64。")
    aliases = configured_player_aliases(config)
    summaries = fetch_player_summaries(session, key, steam_ids)
    rows: list[dict[str, Any]] = []
    for steam_id in steam_ids:
        player = summaries.get(steam_id)
        if not player:
            continue
        state = int(player.get("personastate") or 0)
        game_id = str(player.get("gameid") or "").strip()
        if not game_id:
            continue
        rows.append(
            {
                "steam_id": steam_id,
                "name": display_name(player, aliases),
                "state": state,
                "state_text": persona_state_text(state),
                "game_id": game_id,
                "game_name": str(player.get("gameextrainfo") or "").strip(),
                "avatar": str(player.get("avatarfull") or player.get("avatarmedium") or ""),
            }
        )
    rows.sort(key=lambda item: str(item.get("name") or "").casefold())
    return rows


def build_status_overview_image(
    rows: list[dict[str, Any]],
    output_path: Path = STATUS_OVERVIEW_IMAGE_PATH,
    display_limit: int = 24,
) -> Path:
    session = make_session()
    display_rows = rows[: max(1, min(int(display_limit or 24), 40))]
    columns = 2
    gap = 18
    card_width = (WIDTH - PADDING * 2 - gap) // columns
    cover_height = 196
    card_height = 300
    grid_rows = max(1, (len(display_rows) + columns - 1) // columns)
    height = 330 if not display_rows else 166 + grid_rows * (card_height + gap) + 38
    image = gradient_background(WIDTH, height)
    draw = ImageDraw.Draw(image)
    draw.text((PADDING, 28), "Steam 正在游戏", fill=TEXT, font=FONT_TITLE)
    draw.text(
        (PADDING, 84),
        f"{len(rows)} 位好友正在游戏",
        fill=MUTED,
        font=FONT_SUBTITLE,
    )
    if len(rows) > len(display_rows):
        draw.text(
            (WIDTH - PADDING, 90),
            f"图片展示前 {len(display_rows)} 人",
            fill=MUTED,
            font=FONT_SMALL,
            anchor="ra",
        )

    if not display_rows:
        draw.rounded_rectangle(
            (PADDING, 132, WIDTH - PADDING, 250),
            radius=16,
            fill=PANEL,
            outline=LINE,
            width=1,
        )
        draw.text(
            (WIDTH // 2, 191),
            "现在没有好友在游戏",
            fill=MUTED,
            font=FONT_SECTION,
            anchor="mm",
        )

    for index, row in enumerate(display_rows):
        column = index % columns
        line = index // columns
        x = PADDING + column * (card_width + gap)
        y = 132 + line * (card_height + gap)
        draw.rounded_rectangle(
            (x, y, x + card_width, y + card_height),
            radius=16,
            fill=PANEL if column == 0 else PANEL_2,
            outline=GREEN,
            width=2,
        )

        game_name = str(row.get("game_name") or "未知游戏")
        header = fetch_app_header(session, str(row.get("game_id") or ""))
        header = header or placeholder_image(card_width - 4, cover_height, game_name)
        paste_rounded(
            image,
            header,
            (x + 2, y + 2),
            (card_width - 4, cover_height),
            14,
        )
        draw.line(
            (x + 2, y + cover_height, x + card_width - 2, y + cover_height),
            fill=GREEN,
            width=2,
        )

        avatar = None
        try:
            avatar = image_from_url(session, str(row.get("avatar") or ""))
        except Exception:
            avatar = None
        avatar = avatar or placeholder_image(82, 82, "S")
        paste_rounded(image, avatar, (x + 18, y + 216), (68, 68), 34)

        text_x = x + 104
        text_width = card_width - 124
        draw.text(
            (text_x, y + 207),
            fit_text(draw, str(row.get("name") or "Steam 玩家"), FONT_CARD_TITLE, text_width),
            fill=TEXT,
            font=FONT_CARD_TITLE,
        )

        draw.text(
            (text_x, y + 251),
            fit_text(draw, game_name, FONT_CARD_TEXT, text_width),
            fill=GREEN,
            font=FONT_CARD_TEXT,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=88, optimize=True)
    return output_path


def build_status_overview_update(config: dict[str, Any]) -> tuple[str, Path, list[dict[str, Any]]]:
    rows = status_overview_rows(config)
    display_limit = int(config.get("steam_status_overview_limit") or 24)
    image_path = build_status_overview_image(rows, display_limit=display_limit)
    caption = f"Steam：当前 {len(rows)} 位好友正在游戏"
    return caption, image_path, rows


def build_status_card(event: dict[str, Any], output_path: Path = STATUS_IMAGE_PATH) -> tuple[str, Path]:
    session = make_session()
    player = event.get("player") if isinstance(event.get("player"), dict) else {}
    name = str(event.get("player_name") or player.get("personaname") or "Steam 玩家")
    game_name = str(event.get("game_name") or "正在玩游戏")
    appid = str(event.get("game_id") or "")
    action = str(event.get("action") or "start")
    verb = "切换到了" if action == "switch" else "打开了"
    action_text = "切换游戏" if action == "switch" else "开始游戏"

    image = gradient_background(WIDTH, 720)
    draw = ImageDraw.Draw(image)
    draw.text((PADDING, 28), "Steam 好友动态", fill=TEXT, font=FONT_TITLE)
    draw.text((PADDING, 84), f"{name} · {action_text}", fill=MUTED, font=FONT_SUBTITLE)

    cover_y = 132
    cover_width = WIDTH - PADDING * 2
    cover_height = 418
    header = fetch_app_header(session, appid) or placeholder_image(cover_width, cover_height, game_name)
    paste_rounded(image, header, (PADDING, cover_y), (cover_width, cover_height), 18)
    draw.rounded_rectangle(
        (PADDING, cover_y, WIDTH - PADDING, cover_y + cover_height),
        radius=18,
        outline=GREEN,
        width=3,
    )

    avatar = None
    try:
        avatar = image_from_url(session, str(player.get("avatarfull") or player.get("avatarmedium") or ""))
    except Exception:
        avatar = None
    avatar = avatar or placeholder_image(84, 84, "S")
    paste_rounded(image, avatar, (PADDING + 18, 582), (84, 84), 42)

    text_x = PADDING + 126
    draw.text(
        (text_x, 580),
        fit_text(draw, name, FONT_CARD_TITLE, WIDTH - text_x - PADDING),
        fill=TEXT,
        font=FONT_CARD_TITLE,
    )
    draw.text(
        (text_x, 624),
        fit_text(draw, f"{verb}《{game_name}》", FONT_CARD_TEXT, WIDTH - text_x - PADDING),
        fill=GREEN,
        font=FONT_CARD_TEXT,
    )

    now = datetime.now().strftime("%H:%M")
    draw.text((WIDTH - PADDING, 682), f"{now} 检测到 Steam 状态变化", fill=MUTED, font=FONT_SMALL, anchor="ra")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=88, optimize=True)
    caption = f"{name} 刚刚{verb}《{game_name}》，现在正在游戏中。"
    return caption, output_path


def collect_status_events(config: dict[str, Any]) -> list[dict[str, Any]]:
    key = require_api_key(config)
    session = make_session()
    steam_ids = monitored_steam_ids(config, session=session)
    if not steam_ids:
        return []
    aliases = configured_player_aliases(config)
    summaries = fetch_player_summaries(session, key, steam_ids)
    state = load_state()
    players_state = state.setdefault("players", {})
    initialized = bool(state.get("status_initialized"))
    events: list[dict[str, Any]] = []
    now_ts = time.time()
    repeat_seconds = max(0, int(config.get("steam_status_repeat_minutes") or 120) * 60)
    announce_initial = config_bool(config.get("steam_status_announce_initial"), False)

    for steam_id in steam_ids:
        player = summaries.get(steam_id)
        if not player:
            continue
        player_state = players_state.setdefault(steam_id, {})
        current_game_id = str(player.get("gameid") or "").strip()
        current_game_name = str(player.get("gameextrainfo") or "").strip()
        previous_game_id = str(player_state.get("game_id") or "").strip()
        previous_announce_at = float(player_state.get("last_announce_at") or 0)
        previous_announce_game_id = str(player_state.get("last_announce_game_id") or "").strip()
        action = ""
        if current_game_id:
            if previous_game_id and previous_game_id != current_game_id:
                action = "switch"
            elif not previous_game_id and (initialized or announce_initial):
                action = "start"
            if (
                action
                and current_game_id == previous_announce_game_id
                and repeat_seconds
                and now_ts - previous_announce_at < repeat_seconds
            ):
                action = ""

        player_state.update(
            {
                "game_id": current_game_id,
                "game_name": current_game_name,
                "personaname": str(player.get("personaname") or ""),
                "avatarfull": str(player.get("avatarfull") or ""),
                "updated_at": int(now_ts),
            }
        )
        if action:
            player_state["last_announce_at"] = int(now_ts)
            player_state["last_announce_game_id"] = current_game_id
            events.append(
                {
                    "action": action,
                    "steam_id": steam_id,
                    "player": player,
                    "player_name": display_name(player, aliases),
                    "game_id": current_game_id,
                    "game_name": current_game_name or "未知游戏",
                }
            )

    state["status_initialized"] = True
    save_state(state)
    return events


def playtime_snapshot(config: dict[str, Any], steam_ids: list[str], session: requests.Session | None = None) -> dict[str, Any]:
    key = require_api_key(config)
    session = session or make_session()
    summaries = fetch_player_summaries(session, key, steam_ids)
    aliases = configured_player_aliases(config)
    snapshot: dict[str, Any] = {}
    for steam_id in steam_ids:
        games = fetch_owned_games(session, key, steam_id)
        game_map: dict[str, dict[str, Any]] = {}
        total = 0
        for game in games:
            if not isinstance(game, dict):
                continue
            appid = str(game.get("appid") or "").strip()
            if not appid:
                continue
            minutes = int(game.get("playtime_forever") or 0)
            total += minutes
            game_map[appid] = {
                "name": str(game.get("name") or f"App {appid}"),
                "minutes": minutes,
            }
        player = summaries.get(steam_id, {})
        snapshot[steam_id] = {
            "steam_id": steam_id,
            "name": display_name(player, aliases),
            "avatar": str(player.get("avatarfull") or ""),
            "total_minutes": total,
            "games": game_map,
        }
    return snapshot


def rank_rows_from_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for steam_id, current_item in current.items():
        if not isinstance(current_item, dict):
            continue
        previous_item = previous.get(steam_id) if isinstance(previous, dict) else {}
        if not isinstance(previous_item, dict):
            previous_item = {}
        current_games = current_item.get("games") if isinstance(current_item.get("games"), dict) else {}
        previous_games = previous_item.get("games") if isinstance(previous_item.get("games"), dict) else {}
        game_deltas: list[dict[str, Any]] = []
        total_delta = 0
        for appid, game in current_games.items():
            if not isinstance(game, dict):
                continue
            now_minutes = int(game.get("minutes") or 0)
            prev_game = previous_games.get(appid) if isinstance(previous_games, dict) else {}
            prev_minutes = int(prev_game.get("minutes") or 0) if isinstance(prev_game, dict) else 0
            delta = max(0, now_minutes - prev_minutes)
            if delta <= 0:
                continue
            total_delta += delta
            game_deltas.append({"appid": appid, "name": str(game.get("name") or f"App {appid}"), "minutes": delta})
        game_deltas.sort(key=lambda item: int(item.get("minutes") or 0), reverse=True)
        rows.append(
            {
                "steam_id": steam_id,
                "name": str(current_item.get("name") or steam_id),
                "avatar": str(current_item.get("avatar") or ""),
                "minutes": total_delta,
                "games": game_deltas[:3],
            }
        )
    rows.sort(key=lambda item: int(item.get("minutes") or 0), reverse=True)
    return rows


def build_rank_image(rows: list[dict[str, Any]], output_path: Path = RANK_IMAGE_PATH) -> Path:
    session = make_session()
    display_rows = [row for row in rows if int(row.get("minutes") or 0) > 0][:12]
    row_h = 104
    height = 190 + max(1, len(display_rows)) * row_h + 56
    image = gradient_background(WIDTH, height)
    draw = ImageDraw.Draw(image)
    now = datetime.now()
    draw.text((PADDING, 34), "Steam 每日游玩榜", fill=TEXT, font=FONT_TITLE)
    draw.text((PADDING, 88), f"{now:%Y-%m-%d} 按两次快照之间新增游玩时长统计", fill=MUTED, font=FONT_SUBTITLE)

    y = 150
    if not display_rows:
        draw.rounded_rectangle((PADDING, y, WIDTH - PADDING, y + 120), radius=18, fill=PANEL, outline=LINE, width=2)
        draw.text((PADDING + 28, y + 32), "今天还没看到新增游玩时长。", fill=TEXT, font=FONT_SECTION)
        draw.text((PADDING + 28, y + 76), "如果是第一次启用，明天开始会更准。", fill=MUTED, font=FONT_CARD_TEXT)
    for index, row in enumerate(display_rows, 1):
        draw.rounded_rectangle((PADDING, y, WIDTH - PADDING, y + row_h - 14), radius=16, fill=PANEL, outline=LINE, width=1)
        avatar = None
        try:
            avatar = image_from_url(session, str(row.get("avatar") or ""))
        except Exception:
            avatar = None
        avatar = avatar or placeholder_image(70, 70, "S")
        paste_rounded(image, avatar, (PADDING + 22, y + 13), (70, 70), 35)
        draw.text((PADDING + 110, y + 17), f"#{index}", fill=YELLOW if index <= 3 else BLUE, font=FONT_CARD_TITLE)
        draw.text((PADDING + 165, y + 17), fit_text(draw, str(row.get("name") or ""), FONT_CARD_TITLE, 285), fill=TEXT, font=FONT_CARD_TITLE)
        draw.text((WIDTH - PADDING - 190, y + 17), format_minutes(int(row.get("minutes") or 0)), fill=GREEN, font=FONT_CARD_TITLE)
        games = row.get("games") if isinstance(row.get("games"), list) else []
        game_text = " / ".join(
            f"{str(game.get('name') or '')} +{format_minutes(int(game.get('minutes') or 0))}"
            for game in games[:3]
            if isinstance(game, dict)
        )
        draw.text((PADDING + 165, y + 58), fit_text(draw, game_text or "暂无新增游戏时长", FONT_CARD_TEXT, 610), fill=MUTED, font=FONT_CARD_TEXT)
        y += row_h

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=88, optimize=True)
    return output_path


def build_playtime_rank_update(config: dict[str, Any], update_snapshot: bool = False) -> tuple[str, Path, list[dict[str, Any]]]:
    session = make_session()
    steam_ids = monitored_steam_ids(config, session=session)
    if not steam_ids:
        raise ValueError("Steam players have not been configured.")
    state = load_state()
    previous = state.get("playtime_snapshots") if isinstance(state.get("playtime_snapshots"), dict) else {}
    current = playtime_snapshot(config, steam_ids, session=session)
    rows = rank_rows_from_snapshots(previous, current) if previous else []
    image_path = build_rank_image(rows)
    if update_snapshot:
        state["playtime_snapshots"] = current
        state.setdefault("rank", {})["last_snapshot_at"] = int(time.time())
        save_state(state)
    if previous:
        caption = "Steam 每日游玩排行榜"
    else:
        caption = "Steam 游玩时长榜基准已建立，下一次会统计新增时长"
    return caption, image_path, rows


def should_send_daily_rank(config: dict[str, Any], now: datetime | None = None) -> bool:
    if not config_bool(config.get("steam_rank_enabled"), True):
        return False
    now = now or datetime.now()
    hour = max(0, min(int(config.get("steam_rank_hour") or 22), 23))
    minute = max(0, min(int(config.get("steam_rank_minute") or 0), 59))
    if (now.hour, now.minute) < (hour, minute):
        return False
    state = load_state()
    rank = state.get("rank") if isinstance(state.get("rank"), dict) else {}
    return str(rank.get("last_sent_date") or "") != now.strftime("%Y-%m-%d")


def mark_daily_rank_sent(now: datetime | None = None) -> None:
    now = now or datetime.now()
    state = load_state()
    rank = state.setdefault("rank", {})
    rank["last_sent_date"] = now.strftime("%Y-%m-%d")
    rank["last_sent_at"] = int(time.time())
    save_state(state)


def current_status_text(config: dict[str, Any]) -> str:
    key = require_api_key(config)
    session = make_session()
    steam_ids = monitored_steam_ids(config, session=session)
    if not steam_ids:
        return "还没配置 SteamID64。"
    aliases = configured_player_aliases(config)
    summaries = fetch_player_summaries(session, key, steam_ids)
    playing: list[str] = []
    online = 0
    for steam_id in steam_ids:
        player = summaries.get(steam_id)
        if not player:
            continue
        if int(player.get("personastate") or 0) > 0:
            online += 1
        game_id = str(player.get("gameid") or "").strip()
        if game_id:
            playing.append(f"{display_name(player, aliases)}：《{player.get('gameextrainfo') or '未知游戏'}》")
    if playing:
        return "现在 Steam 上有人在玩：\n" + "\n".join(f"- {item}" for item in playing[:12])
    return f"现在没看到有人在 Steam 上开游戏。在线人数：{online}/{len(steam_ids)}"
