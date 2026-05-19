#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG_PATH="${QQ_BOT_CONFIG:-$ROOT/qq_bot_config.json}"
VENV_PATH="${VENV_PATH:-$ROOT/.venv}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing QQ bot config: $CONFIG_PATH" >&2
  echo "Copy qq_bot_config.example.json to qq_bot_config.json and edit it first." >&2
  exit 1
fi

if [[ ! -d "$VENV_PATH" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python send_wolf.py --config "$CONFIG_PATH"
