#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

python3 - <<'PY'
import json
from pathlib import Path

path = Path("gemini_bot_config.json")
if not path.exists():
    raise SystemExit("gemini_bot_config.json not found. Run this in the project directory.")

data = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("gemini_bot_config.json must be a JSON object.")

data.update(
    {
        "proactive_topic_enabled": True,
        "proactive_topic_min_interval_minutes": 120,
        "proactive_topic_max_interval_minutes": 480,
        "proactive_topic_idle_minutes": 45,
        "proactive_topic_daily_limit": 4,
        "proactive_topic_active_start_hour": 9,
        "proactive_topic_active_end_hour": 23,
        "proactive_topic_check_seconds": 300,
        "proactive_topic_weather_enabled": True,
    }
)

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Enabled proactive topics in gemini_bot_config.json.")
PY

echo "Restarting QQ bot..."
pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &
sleep 3
tail -n 30 gemini_bot.log
