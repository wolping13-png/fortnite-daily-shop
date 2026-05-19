#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

if [ -f gemini_bot_config.json ]; then
  python3 - <<'PY'
import json
from pathlib import Path

path = Path("gemini_bot_config.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["reddit_pet_enabled"] = False
data.pop("pet_command", None)
data.pop("reddit_pet_limit", None)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  echo "Disabled Reddit pet triggers in gemini_bot_config.json."
else
  echo "gemini_bot_config.json not found, skipped config update."
fi

existing_cron="$(mktemp)"
new_cron="$(mktemp)"
crontab -l > "$existing_cron" 2>/dev/null || true
grep -v "run_reddit_pets.sh" "$existing_cron" > "$new_cron" || true
crontab "$new_cron"
rm -f "$existing_cron" "$new_cron"
echo "Removed Reddit pet cron task if it existed."

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "Reddit pet feature is disabled. Messages like 狼狼 / 来点狼狼 will no longer trigger image fetching."
