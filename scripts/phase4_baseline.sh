#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  DC=(docker compose)
fi

dc() {
  "${DC[@]}" "$@"
}

for cmd in docker curl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Missing command: $cmd"
    exit 1
  fi
done

mkdir -p config logs backup_config downloads
if [[ ! -f config/URL_config.ini ]]; then
  touch config/URL_config.ini
fi

wait_health() {
  local retries=60
  local i
  for ((i = 1; i <= retries; i++)); do
    if curl -fsS "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "[ERROR] health check timeout"
  return 1
}

api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" "http://127.0.0.1:8000$path" \
      -H "Content-Type: application/json" \
      -d "$body"
  else
    curl -fsS -X "$method" "http://127.0.0.1:8000$path"
  fi
}

assert_json() {
  local json_payload="$1"
  local python_expr="$2"
  local error_message="$3"

  if ! JSON_PAYLOAD="$json_payload" PY_EXPR="$python_expr" python3 - <<'PY'
import json
import os
import sys

payload = os.environ["JSON_PAYLOAD"]
expr = os.environ["PY_EXPR"]
obj = json.loads(payload)
if not bool(eval(expr, {}, {"obj": obj})):
    sys.exit(1)
PY
  then
    echo "[ERROR] ${error_message}"
    echo "[DEBUG] payload: ${json_payload}"
    exit 1
  fi
}

TEST_SUFFIX="$(date +%s)"
TEST_URL="https://live.douyin.com/phase4-${TEST_SUFFIX}"
ENCODED_TEST_URL="$(TEST_URL="$TEST_URL" python3 - <<'PY'
import os
import urllib.parse
print(urllib.parse.quote(os.environ["TEST_URL"], safe=""))
PY
)"

echo "[INFO] Phase 4 baseline started"
echo "[INFO] Test URL: ${TEST_URL}"

echo "[STEP] Build and start container"
dc up -d --build
wait_health

echo "[STEP] Create task"
CREATE_RESP="$(api POST /api/v1/tasks "{\"url\":\"${TEST_URL}\",\"quality\":\"原画\",\"anchor_name\":\"phase4-baseline\"}")"
assert_json "$CREATE_RESP" "obj.get('item', {}).get('url') == '${TEST_URL}'" "create task failed"

echo "[STEP] List tasks"
LIST_RESP="$(api GET /api/v1/tasks)"
assert_json "$LIST_RESP" "any(item.get('url') == '${TEST_URL}' for item in obj.get('items', []))" "task not found in list"

echo "[STEP] Update task"
UPDATE_RESP="$(api PUT /api/v1/tasks/${ENCODED_TEST_URL} "{\"quality\":\"高清\",\"anchor_name\":\"phase4-updated\",\"enabled\":true}")"
assert_json "$UPDATE_RESP" "obj.get('item', {}).get('quality') == '高清' and obj.get('item', {}).get('anchor_name') == 'phase4-updated'" "update task failed"

echo "[STEP] Start task"
START_RESP="$(api POST /api/v1/tasks/${ENCODED_TEST_URL}/start)"
assert_json "$START_RESP" "obj.get('item', {}).get('enabled') is True" "start task failed"

echo "[STEP] Stop task (disable=false)"
STOP_RESP="$(api POST /api/v1/tasks/${ENCODED_TEST_URL}/stop?disable=false)"
assert_json "$STOP_RESP" "obj.get('item', {}).get('enabled') is True" "stop task disable=false failed"

echo "[STEP] Stop task (disable=true)"
DISABLE_RESP="$(api POST /api/v1/tasks/${ENCODED_TEST_URL}/stop?disable=true)"
assert_json "$DISABLE_RESP" "obj.get('item', {}).get('enabled') is False" "stop task disable=true failed"

if ! TEST_URL="$TEST_URL" python3 - <<'PY'
from pathlib import Path
import os
import sys

target = os.environ["TEST_URL"]
config_file = Path("config/URL_config.ini")
if not config_file.exists():
    sys.exit(1)

lines = config_file.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
ok = any(line.lstrip().startswith("#") and target in line for line in lines)
sys.exit(0 if ok else 1)
PY
then
  echo "[ERROR] URL_config.ini does not contain disabled task marker for ${TEST_URL}"
  echo "[DEBUG] URL_config.ini content:"
  cat config/URL_config.ini
  exit 1
fi

echo "[STEP] Restart app and verify recovery"
dc restart app
wait_health
POST_RESTART_RESP="$(api GET /api/v1/tasks)"
assert_json "$POST_RESTART_RESP" "any(item.get('url') == '${TEST_URL}' and item.get('enabled') is False for item in obj.get('items', []))" "restart recovery failed"

echo "[STEP] Graceful stop verification"
CONTAINER_ID="$(dc ps -q app)"
if [[ -z "$CONTAINER_ID" ]]; then
  echo "[ERROR] app container id not found"
  exit 1
fi

dc stop -t 35 app
SHUTDOWN_LOGS="$(dc logs --no-color app 2>/dev/null || true)"
if [[ "$SHUTDOWN_LOGS" != *"runtime shutdown requested="* && "$SHUTDOWN_LOGS" != *"Application shutdown complete."* ]]; then
  echo "[ERROR] shutdown log marker not found"
  echo "[DEBUG] Last logs:" 
  echo "$SHUTDOWN_LOGS" | tail -n 60
  exit 1
fi

dc up -d app
wait_health

echo "[STEP] Delete task"
DELETE_RESP="$(api DELETE /api/v1/tasks/${ENCODED_TEST_URL})"
assert_json "$DELETE_RESP" "obj.get('deleted') is True" "delete task failed"

FINAL_RESP="$(api GET /api/v1/tasks)"
assert_json "$FINAL_RESP" "not any(item.get('url') == '${TEST_URL}' for item in obj.get('items', []))" "task still exists after delete"

echo "[PASS] Phase 4 baseline completed successfully"
