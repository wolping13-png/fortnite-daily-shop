#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

mkdir -p memes/{default,happy,confused,thinking,comfort,sleep,food,game,wolf}

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
        "meme_enabled": True,
        "meme_dir": "memes",
        "meme_chance": 0.28,
        "meme_cooldown_seconds": 240,
        "meme_max_per_hour": 8,
        "meme_max_text_length": 180,
    }
)

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Enabled contextual memes in gemini_bot_config.json.")
PY

echo "Meme folders:"
find memes -maxdepth 1 -mindepth 1 -type d | sort
echo
echo "Put images into these folders, then restart the QQ bot:"
echo "pkill -f qq_gemini_bot.py 2>/dev/null || true"
echo "nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &"
