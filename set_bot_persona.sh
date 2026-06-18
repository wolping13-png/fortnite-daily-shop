#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f wendell_persona.txt ]; then
  echo "Missing wendell_persona.txt"
  exit 1
fi

if [ ! -f gemini_bot_config.json ]; then
  cp gemini_bot_config.example.json gemini_bot_config.json
fi

python3 - <<'PY'
import json
from pathlib import Path

config_path = Path("gemini_bot_config.json")
persona_path = Path("wendell_persona.txt")

data = json.loads(config_path.read_text(encoding="utf-8"))
data["system_prompt"] = persona_path.read_text(encoding="utf-8").strip()
config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "Bot persona updated from wendell_persona.txt."
