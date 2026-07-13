#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_SCRIPT="$ROOT/run_everyday_one_wendell.sh"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/everyday_one_wendell.log"
MARK_BEGIN="# BEGIN EveryDayOneWendellQQ"
MARK_END="# END EveryDayOneWendellQQ"
OLD_MARK_BEGIN="# BEGIN EveryOneWendellQQ"
OLD_MARK_END="# END EveryOneWendellQQ"
CRON_TIME="${CRON_TIME:-0 14 * * *}"
CRON_TZ_VALUE="${CRON_TZ_VALUE:-Asia/Shanghai}"

mkdir -p "$LOG_DIR"
chmod +x "$TASK_SCRIPT"

existing_cron="$(mktemp)"
new_cron="$(mktemp)"
crontab -l > "$existing_cron" 2>/dev/null || true

awk -v begin="$MARK_BEGIN" -v end="$MARK_END" -v old_begin="$OLD_MARK_BEGIN" -v old_end="$OLD_MARK_END" '
  $0 == begin || $0 == old_begin { skip = 1; next }
  $0 == end || $0 == old_end { skip = 0; next }
  skip != 1 { print }
' "$existing_cron" > "$new_cron"

{
  echo "$MARK_BEGIN"
  echo "CRON_TZ=$CRON_TZ_VALUE"
  echo "$CRON_TIME cd \"$ROOT\" && \"$TASK_SCRIPT\" >> \"$LOG_FILE\" 2>&1"
  echo "$MARK_END"
} >> "$new_cron"

crontab "$new_cron"
rm -f "$existing_cron" "$new_cron"

echo "Installed EveryDayOneWendell cron task."
echo "Schedule: $CRON_TIME ($CRON_TZ_VALUE)"
echo "Log file: $LOG_FILE"
