#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_SCRIPT="$ROOT/run_game_deals_qq.sh"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/game_deals_daily.log"
MARK_BEGIN="# BEGIN GameDealsQQ"
MARK_END="# END GameDealsQQ"

# Run at 10:05 in the server's local timezone.
# Before installing, set the server timezone with:
#   timedatectl set-timezone Asia/Shanghai
CRON_TIME="${CRON_TIME:-5 10 * * *}"

mkdir -p "$LOG_DIR"
chmod +x "$TASK_SCRIPT"

existing_cron="$(mktemp)"
new_cron="$(mktemp)"

crontab -l > "$existing_cron" 2>/dev/null || true

awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
  $0 == begin { skip = 1; next }
  $0 == end { skip = 0; next }
  skip != 1 { print }
' "$existing_cron" > "$new_cron"

{
  echo "$MARK_BEGIN"
  echo "$CRON_TIME cd \"$ROOT\" && \"$TASK_SCRIPT\" >> \"$LOG_FILE\" 2>&1"
  echo "$MARK_END"
} >> "$new_cron"

crontab "$new_cron"
rm -f "$existing_cron" "$new_cron"

echo "Installed game deals cron task."
echo "Schedule: $CRON_TIME"
echo "Log file: $LOG_FILE"
echo "Recommended timezone: Asia/Shanghai"
echo "Keep NapCatQQ running and logged in before the scheduled time."
