#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f gemini_bot_config.json ]; then
  cp gemini_bot_config.example.json gemini_bot_config.json
fi

printf "Paste OpenRouter API Key: "
read -rs OPENROUTER_API_KEY
printf "\n"

if [ -z "$OPENROUTER_API_KEY" ]; then
  echo "OpenRouter API Key is empty."
  exit 1
fi

export OPENROUTER_API_KEY
python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path("gemini_bot_config.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["provider"] = "openrouter"
data["openrouter_api_key"] = os.environ["OPENROUTER_API_KEY"].strip()
data.setdefault("openrouter_base_url", "https://openrouter.ai/api/v1")
data.setdefault("openrouter_site_url", "")
data.setdefault("openrouter_app_name", "Wendell QQ Bot")
data["model"] = "thedrummer/cydonia-24b-v4.1"
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "OpenRouter is configured. Try: @机器人 你好"
