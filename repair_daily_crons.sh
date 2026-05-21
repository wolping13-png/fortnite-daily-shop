#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

mkdir -p logs

if command -v timedatectl >/dev/null 2>&1; then
  timedatectl set-timezone Asia/Shanghai 2>/dev/null || true
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now cron 2>/dev/null || systemctl enable --now crond 2>/dev/null || true
else
  service cron start 2>/dev/null || service crond start 2>/dev/null || true
fi

chmod +x \
  run_daily_qq.sh \
  run_game_deals_qq.sh \
  run_everyday_one_wolf.sh \
  run_bedtime_reminder.sh \
  install_cloud_cron.sh \
  install_game_deals_cron.sh \
  install_everyday_one_wolf_cron.sh \
  install_bedtime_reminder_cron.sh

bash install_cloud_cron.sh
bash install_game_deals_cron.sh
bash install_everyday_one_wolf_cron.sh
bash install_bedtime_reminder_cron.sh

echo
echo "Current time:"
date
echo
echo "Installed crontab:"
crontab -l
echo
echo "Cron service:"
if command -v systemctl >/dev/null 2>&1; then
  systemctl status cron --no-pager 2>/dev/null || systemctl status crond --no-pager 2>/dev/null || true
else
  service cron status 2>/dev/null || service crond status 2>/dev/null || true
fi
