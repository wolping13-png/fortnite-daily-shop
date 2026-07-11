#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f gemini_bot_config.json ]; then
  cp gemini_bot_config.example.json gemini_bot_config.json
fi

printf "Paste Steam Web API Key: "
read -rs STEAM_API_KEY
printf "\n"

if [ -z "$STEAM_API_KEY" ]; then
  echo "Steam Web API Key is empty."
  exit 1
fi

printf "Paste SteamID64 list, separated by comma: "
read -r STEAM_IDS

if [ -z "$STEAM_IDS" ]; then
  echo "SteamID64 list is empty."
  exit 1
fi

printf "Optional QQ group IDs for Steam messages, separated by comma. Leave empty to use allowed_group_ids: "
read -r STEAM_GROUP_IDS

export STEAM_API_KEY STEAM_IDS STEAM_GROUP_IDS
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

data["steam_status_enabled"] = True
data["steam_api_key"] = os.environ["STEAM_API_KEY"].strip()
data["steam_players"] = [{"steam_id": steam_id, "name": ""} for steam_id in steam_ids]
data.setdefault("steam_friend_source_steam_ids", [])
data.setdefault("steam_friend_limit", 50)
data["steam_group_ids"] = group_ids
data.setdefault("steam_status_command", "Steam状态")
data.setdefault("steam_rank_command", "Steam排行")
data.setdefault("steam_status_check_seconds", 120)
data.setdefault("steam_status_repeat_minutes", 120)
data.setdefault("steam_status_announce_initial", False)
data.setdefault("steam_rank_enabled", True)
data.setdefault("steam_rank_hour", 22)
data.setdefault("steam_rank_minute", 0)

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "Steam monitor is configured. Try: Steam状态"
