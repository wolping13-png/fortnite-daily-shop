#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${1:-$ROOT/gemini_bot_config.json}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing config: $CONFIG_PATH" >&2
  exit 1
fi

read -r -s -p "Paste X Bearer Token: " X_BEARER_TOKEN
echo
X_BEARER_TOKEN="${X_BEARER_TOKEN#Bearer }"
X_BEARER_TOKEN="${X_BEARER_TOKEN#bearer }"

if [[ -z "${X_BEARER_TOKEN// }" ]]; then
  echo "Token is empty." >&2
  exit 1
fi

python3 - "$CONFIG_PATH" "$X_BEARER_TOKEN" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
token = sys.argv[2].strip()
data = json.loads(path.read_text(encoding="utf-8"))

data["x_bearer_token"] = token
data.setdefault("x_search_command", "X宠物")
data.setdefault("x_search_limit", 3)
data.setdefault("x_search_fetch_limit", 30)
data.setdefault(
    "x_search_query",
    "(cat OR dog OR wolf OR fox OR 宠物 OR 猫 OR 狗 OR 狼 OR 狐狸) has:media -is:retweet",
)

tmp = path.with_suffix(path.suffix + ".tmp")
tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
tmp.replace(path)
PY

echo "X Bearer Token saved to $CONFIG_PATH"
