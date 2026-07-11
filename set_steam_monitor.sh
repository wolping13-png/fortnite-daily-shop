#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f gemini_bot_config.json ]; then
  cp gemini_bot_config.example.json gemini_bot_config.json
fi

printf "Paste Steam Web API Key, or press Enter to keep the current value: "
read -rs STEAM_API_KEY
printf "\n"

printf "Paste SteamID64 list separated by comma, or press Enter to keep the current list: "
read -r STEAM_IDS

printf "Automatically read the public friend lists of these accounts? [Y/n]: "
read -r STEAM_AUTO_FRIENDS

printf "Optional QQ group IDs for Steam messages, separated by comma. Leave empty to use allowed_group_ids: "
read -r STEAM_GROUP_IDS

export STEAM_API_KEY STEAM_IDS STEAM_AUTO_FRIENDS STEAM_GROUP_IDS
python3 - <<'PY'
import json
import os
import re
from pathlib import Path

path = Path("gemini_bot_config.json")
data = json.loads(path.read_text(encoding="utf-8"))

def ids_from_env(name):
    values = []
    for item in re.split(r"[,，\s]+", os.environ.get(name, "").strip()):
        item = item.strip()
        if item and item.isdigit() and item not in values:
            values.append(item)
    return values

steam_ids = ids_from_env("STEAM_IDS")
group_ids = ids_from_env("STEAM_GROUP_IDS")
if not steam_ids:
    for item in data.get("steam_players", []):
        steam_id = str(item.get("steam_id", "") if isinstance(item, dict) else item).strip()
        if steam_id.isdigit() and steam_id not in steam_ids:
            steam_ids.append(steam_id)
    for item in data.get("steam_player_ids", []):
        steam_id = str(item).strip()
        if steam_id.isdigit() and steam_id not in steam_ids:
            steam_ids.append(steam_id)

steam_api_key = os.environ.get("STEAM_API_KEY", "").strip() or str(data.get("steam_api_key") or "").strip()
if not steam_api_key:
    raise SystemExit("Steam Web API Key is empty.")
if not steam_ids:
    raise SystemExit("SteamID64 list is empty.")

data["steam_status_enabled"] = True
data["steam_api_key"] = steam_api_key
data["steam_players"] = [{"steam_id": steam_id, "name": ""} for steam_id in steam_ids]
auto_friends = os.environ.get("STEAM_AUTO_FRIENDS", "").strip().lower()
if auto_friends not in {"n", "no", "0", "false"}:
    data["steam_friend_source_steam_ids"] = steam_ids
else:
    data["steam_friend_source_steam_ids"] = []
data.setdefault("steam_friend_limit", 50)
data.setdefault("steam_status_overview_limit", 24)
if group_ids:
    data["steam_group_ids"] = group_ids
else:
    data.setdefault("steam_group_ids", [])
data.setdefault("steam_status_command", "Steam状态")
data.setdefault("steam_rank_command", "Steam排行")
data.setdefault("steam_status_check_seconds", 120)
data.setdefault("steam_status_repeat_minutes", 120)
data["steam_status_announce_initial"] = True
data.setdefault("steam_rank_enabled", True)
data.setdefault("steam_rank_hour", 22)
data.setdefault("steam_rank_minute", 0)

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

state_path = Path("bot_memory/steam_status.json")
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if not isinstance(state, dict):
        state = {}
    state["players"] = {}
    state["status_initialized"] = False
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "Steam monitor is configured. Public friend lists will be read automatically when enabled. Try: Steam状态"
