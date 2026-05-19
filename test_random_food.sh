#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PATH="${VENV_PATH:-$ROOT/.venv}"

if [[ ! -d "$VENV_PATH" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [[ -z "${TAVILY_API_KEY:-}" && -f gemini_bot_config.json ]]; then
  export TAVILY_API_KEY="$(
    python - <<'PY'
import json
from pathlib import Path

path = Path("gemini_bot_config.json")
data = json.loads(path.read_text(encoding="utf-8"))
print(data.get("tavily_api_key") or "")
PY
  )"
fi

python - <<'PY'
import os
from random_food import build_random_food_recommendation

for kind in ("food", "drink"):
    caption, image_path, item = build_random_food_recommendation(
        kind,
        tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
    )
    print(caption)
    print(image_path)
    print(item.get("image_url", ""))
PY
