#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f gemini_bot_config.json ]; then
  cp gemini_bot_config.example.json gemini_bot_config.json
fi

python3 - <<'PY'
import json
from pathlib import Path

path = Path("gemini_bot_config.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["provider"] = "openrouter"
data["model"] = "thedrummer/cydonia-24b-v4.1"
data["openrouter_plain_chat"] = True
data["openrouter_plain_history"] = True
data["openrouter_plain_memory"] = True
data["system_prompt"] = ""
data["system_prompt_file"] = "wendell_persona.txt"
data["max_output_tokens"] = 800
data["chat_history_limit"] = 12
data["context_filter_enabled"] = True
data["context_followup_history_limit"] = 4
data["context_standalone_history_limit"] = 2
data["semi_agent_enabled"] = False
data["auto_web_search"] = False
data["web_search_mode"] = "off"
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "OpenRouter plain chat mode is enabled."
