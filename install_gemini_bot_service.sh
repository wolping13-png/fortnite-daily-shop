#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_PATH="/etc/systemd/system/fortnite-gemini-bot.service"

if [[ ! -f "$ROOT/gemini_bot_config.json" ]]; then
  echo "Missing gemini_bot_config.json" >&2
  echo "Copy gemini_bot_config.example.json to gemini_bot_config.json and edit it first." >&2
  exit 1
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  python3 -m venv "$ROOT/.venv"
fi

source "$ROOT/.venv/bin/activate"
python -m pip install -r "$ROOT/requirements.txt"

cat > "$SERVICE_PATH" <<SERVICE
[Unit]
Description=Fortnite QQ Gemini Bot
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python $ROOT/qq_gemini_bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable --now fortnite-gemini-bot
systemctl status fortnite-gemini-bot --no-pager
