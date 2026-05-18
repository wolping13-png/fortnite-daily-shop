#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV_PATH="${VENV_PATH:-$ROOT/.venv}"

if [[ ! -f "$ROOT/gemini_bot_config.json" ]]; then
  echo "Missing gemini_bot_config.json" >&2
  echo "Copy gemini_bot_config.example.json to gemini_bot_config.json and edit it first." >&2
  exit 1
fi

if [[ ! -d "$VENV_PATH" ]]; then
  python3 -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"
python -m pip install -r requirements.txt
python qq_gemini_bot.py
