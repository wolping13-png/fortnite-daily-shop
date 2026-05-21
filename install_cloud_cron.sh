#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_SCRIPT="$ROOT/run_daily_qq.sh"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/qq_daily.log"
MARK_BEGIN="# BEGIN FortniteDailyShopQQ"
MARK_END="# END FortniteDailyShopQQ"

# Run at 08:05 in China mainland time.
CRON_TIME="${CRON_TIME:-5 8 * * *}"
CRON_TZ_VALUE="${CRON_TZ_VALUE:-Asia/Shanghai}"

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
  echo "CRON_TZ=$CRON_TZ_VALUE"
  echo "$CRON_TIME cd \"$ROOT\" && \"$TASK_SCRIPT\" >> \"$LOG_FILE\" 2>&1"
  echo "$MARK_END"
} >> "$new_cron"

crontab "$new_cron"
rm -f "$existing_cron" "$new_cron"

echo "Installed cloud cron task."
echo "Schedule: $CRON_TIME"
echo "Cron timezone: $CRON_TZ_VALUE"
echo "Log file: $LOG_FILE"
echo "Keep NapCatQQ running and logged in before the scheduled time."
