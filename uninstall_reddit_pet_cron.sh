#!/usr/bin/env bash
set -Eeuo pipefail

existing_cron="$(mktemp)"
new_cron="$(mktemp)"

crontab -l > "$existing_cron" 2>/dev/null || true
grep -v "run_reddit_pets.sh" "$existing_cron" > "$new_cron" || true
crontab "$new_cron"

rm -f "$existing_cron" "$new_cron"

echo "Removed Reddit pet cron task if it existed."
