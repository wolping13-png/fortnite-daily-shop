#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${QQ_BOT_CONFIG:-$ROOT/gemini_bot_config.json}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing bot config: $CONFIG_PATH" >&2
  exit 1
fi

if [[ "$#" -lt 1 ]]; then
  echo "Usage: bash setup_everyday_one_wendell.sh GROUP_ID [GROUP_ID ...]" >&2
  exit 1
fi

python3 - "$CONFIG_PATH" "$@" <<'PY'
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
raw_group_ids = sys.argv[2:]
group_ids: list[int] = []
for raw_value in raw_group_ids:
    value = str(raw_value).strip()
    if not value.isdigit():
        raise SystemExit(f"Invalid QQ group ID: {value}")
    group_id = int(value)
    if group_id not in group_ids:
        group_ids.append(group_id)

config = json.loads(config_path.read_text(encoding="utf-8"))
if not isinstance(config, dict):
    raise SystemExit(f"{config_path.name} must contain a JSON object.")

config["everyday_one_wendell_group_ids"] = group_ids
temporary = config_path.with_suffix(config_path.suffix + ".tmp")
temporary.write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.chmod(temporary, stat.S_IMODE(config_path.stat().st_mode))
temporary.replace(config_path)
print("EveryDayOneWendell groups: " + ", ".join(map(str, group_ids)))
PY

bash "$ROOT/install_everyday_one_wendell_cron.sh"

echo "EveryDayOneWendell setup is complete."
