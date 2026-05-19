#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f gemini_bot_config.json ]; then
  cp gemini_bot_config.example.json gemini_bot_config.json
fi

printf "Paste Tavily API Key: "
read -r TAVILY_API_KEY

if [ -z "$TAVILY_API_KEY" ]; then
  echo "Tavily API Key is empty."
  exit 1
fi

export TAVILY_API_KEY
python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path("gemini_bot_config.json")
data = json.loads(path.read_text(encoding="utf-8"))
data["tavily_api_key"] = os.environ["TAVILY_API_KEY"].strip()
data.setdefault("web_search_command", "联网查")
data.setdefault("web_search_depth", "basic")
data.setdefault("web_search_max_results", 5)
data.setdefault("web_search_include_answer", False)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &

sleep 3
tail -n 30 gemini_bot.log
echo "Tavily web search is configured. Try: @机器人 联网查 今天有什么 AI 新闻"
