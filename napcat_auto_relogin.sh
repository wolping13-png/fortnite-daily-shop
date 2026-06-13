#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CONTAINER_NAME="${NAPCAT_CONTAINER:-napcat}"
CONFIG_PATH="${GEMINI_BOT_CONFIG:-$ROOT/gemini_bot_config.json}"
RELOGIN_WAIT_SECONDS="${NAPCAT_RELOGIN_WAIT_SECONDS:-60}"

LOG_PREFIX="[napcat-auto-relogin]"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_PREFIX $*"
}

read_config() {
  python3 - "$CONFIG_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = {}
if path.exists():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        data = {}

print(str(data.get("onebot_http_url") or "http://127.0.0.1:3000").rstrip("/"))
print(str(data.get("access_token") or ""))
print(str(data.get("bot_qq") or ""))
PY
}

check_onebot_online() {
  local base_url="$1"
  local access_token="$2"

  python3 - "$base_url" "$access_token" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base_url = sys.argv[1].rstrip("/")
access_token = sys.argv[2]
request = urllib.request.Request(
    f"{base_url}/get_status",
    data=b"{}",
    headers={"Content-Type": "application/json"},
    method="POST",
)
if access_token:
    request.add_header("Authorization", f"Bearer {access_token}")

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
except Exception as exc:
    print(f"request_failed: {exc}")
    raise SystemExit(2)

payload = data.get("data") if isinstance(data, dict) else {}
online = bool(isinstance(payload, dict) and payload.get("online"))
good = bool(isinstance(payload, dict) and payload.get("good"))
print(f"online={online} good={good}")
raise SystemExit(0 if online and good else 1)
PY
}

if ! command -v docker >/dev/null 2>&1; then
  log "docker command not found."
  exit 1
fi

if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  log "container '$CONTAINER_NAME' not found."
  exit 1
fi

mapfile -t CONFIG_VALUES < <(read_config)
ONEBOT_URL="${CONFIG_VALUES[0]:-http://127.0.0.1:3000}"
ACCESS_TOKEN="${CONFIG_VALUES[1]:-}"
BOT_QQ="${NAPCAT_QQ:-${CONFIG_VALUES[2]:-}}"

if check_onebot_online "$ONEBOT_URL" "$ACCESS_TOKEN"; then
  log "NapCat is online."
  exit 0
fi

log "NapCat looks offline. Restarting container '$CONTAINER_NAME'..."
if [[ -n "$BOT_QQ" ]]; then
  log "Expected quick-login QQ: $BOT_QQ. Make sure this container was created with '-q $BOT_QQ'."
else
  log "NAPCAT_QQ is not set. Restart will only quick-login if the container already has -q in its command."
fi

docker restart "$CONTAINER_NAME" >/dev/null
sleep "$RELOGIN_WAIT_SECONDS"

if check_onebot_online "$ONEBOT_URL" "$ACCESS_TOKEN"; then
  log "NapCat quick relogin succeeded."
  exit 0
fi

log "NapCat is still offline after restart. The QQ login state may be invalid and may require QR scan."
exit 2
