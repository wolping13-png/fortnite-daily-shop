#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

CRON_LINE="30 12 * * * cd $ROOT && bash run_reddit_pets.sh >> $LOG_DIR/reddit_pets.log 2>&1"

(crontab -l 2>/dev/null | grep -v "run_reddit_pets.sh" || true; echo "$CRON_LINE") | crontab -

echo "Installed Reddit pet cron."
echo "It runs every day at 20:30 Beijing time."
