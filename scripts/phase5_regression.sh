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

ORIGINAL_URL_CONFIG="$(mktemp)"
cp config/URL_config.ini "$ORIGINAL_URL_CONFIG"

cleanup() {
  local exit_code=$?
  if [[ -f "$ORIGINAL_URL_CONFIG" ]]; then
    cp "$ORIGINAL_URL_CONFIG" config/URL_config.ini || true
    rm -f "$ORIGINAL_URL_CONFIG" || true
  fi

  if [[ $exit_code -eq 0 ]]; then
    echo "[PASS] Phase 5 regression completed successfully"
  else
    echo "[FAIL] Phase 5 regression failed"
  fi

  exit "$exit_code"
}

trap cleanup EXIT

wait_health() {
  local retries=90
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

encode_url() {
  local raw_url="$1"
  TEST_URL="$raw_url" python3 - <<'PY'
import os
import urllib.parse

print(urllib.parse.quote(os.environ["TEST_URL"], safe=""))
PY
}

json_match() {
  local json_payload="$1"
  local python_expr="$2"

  JSON_PAYLOAD="$json_payload" PY_EXPR="$python_expr" python3 - <<'PY'
import json
import os
import sys

payload = os.environ["JSON_PAYLOAD"]
expr = os.environ["PY_EXPR"]
obj = json.loads(payload)
if not bool(eval(expr, {}, {"obj": obj})):
    sys.exit(1)
PY
}

assert_json() {
  local json_payload="$1"
  local python_expr="$2"
  local error_message="$3"

  if ! json_match "$json_payload" "$python_expr"; then
    echo "[ERROR] ${error_message}"
    echo "[DEBUG] payload: ${json_payload}"
    exit 1
  fi
}

assert_url_config() {
  local python_expr="$1"
  local error_message="$2"

  if ! URL_CONFIG_PATH="config/URL_config.ini" PY_EXPR="$python_expr" python3 - <<'PY'
from pathlib import Path
import os
import sys

path = Path(os.environ["URL_CONFIG_PATH"])
expr = os.environ["PY_EXPR"]
if not path.exists():
    sys.exit(1)

lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
if not bool(eval(expr, {}, {"lines": lines})):
    sys.exit(1)
PY
  then
    echo "[ERROR] ${error_message}"
    echo "[DEBUG] URL_config.ini content:"
    cat config/URL_config.ini
    exit 1
  fi
}

TEST_SUFFIX="$(date +%s)"

COMPAT_URL_A="https://example.com/phase5-legacy-a-${TEST_SUFFIX}"
COMPAT_URL_B="https://example.com/phase5-legacy-b-${TEST_SUFFIX}"
COMPAT_URL_C="https://example.com/phase5-legacy-c-${TEST_SUFFIX}"
COMPAT_URL_D="https://example.com/phase5-legacy-d-${TEST_SUFFIX}"
COMPAT_URL_E="https://example.com/phase5-legacy-e-${TEST_SUFFIX}"
COMPAT_URL_F="https://example.com/phase5-legacy-f-${TEST_SUFFIX}"

CRUD_URL="https://example.com/phase5-crud-${TEST_SUFFIX}"
CRUD_ENCODED_URL="$(encode_url "$CRUD_URL")"
COMPAT_ENCODED_URL_A="$(encode_url "$COMPAT_URL_A")"

echo "[INFO] Phase 5 regression started"

echo "[STEP] Seed legacy-compatible URL_config.ini fixtures"
cat > config/URL_config.ini <<EOF
${COMPAT_URL_A}
高清,${COMPAT_URL_B}
原画,${COMPAT_URL_C},legacy-anchor
#超清,${COMPAT_URL_D},legacy-disabled
#${COMPAT_URL_E}
${COMPAT_URL_F},legacy-two-field
EOF

echo "[STEP] Build and start container"
dc up -d --build
wait_health

echo "[STEP] Compatibility regression: legacy URL_config.ini parsing"
COMPAT_LIST_RESP="$(api GET /api/v1/tasks)"
assert_json "$COMPAT_LIST_RESP" "any(item.get('url') == '${COMPAT_URL_A}' and item.get('quality') == '原画' and item.get('enabled') is True for item in obj.get('items', []))" "legacy single-url line parse failed"
assert_json "$COMPAT_LIST_RESP" "any(item.get('url') == '${COMPAT_URL_B}' and item.get('quality') == '高清' and item.get('enabled') is True for item in obj.get('items', []))" "legacy quality,url line parse failed"
assert_json "$COMPAT_LIST_RESP" "any(item.get('url') == '${COMPAT_URL_C}' and item.get('anchor_name') == 'legacy-anchor' and item.get('enabled') is True for item in obj.get('items', []))" "legacy quality,url,name line parse failed"
assert_json "$COMPAT_LIST_RESP" "any(item.get('url') == '${COMPAT_URL_D}' and item.get('enabled') is False for item in obj.get('items', []))" "legacy disabled quality,url,name line parse failed"
assert_json "$COMPAT_LIST_RESP" "any(item.get('url') == '${COMPAT_URL_E}' and item.get('enabled') is False for item in obj.get('items', []))" "legacy disabled single-url line parse failed"
assert_json "$COMPAT_LIST_RESP" "any(item.get('url') == '${COMPAT_URL_F}' and item.get('anchor_name') == 'legacy-two-field' and item.get('quality') == '原画' for item in obj.get('items', []))" "legacy url,name line parse failed"

echo "[STEP] Compatibility regression: # disable semantics"
DISABLE_A_RESP="$(api POST /api/v1/tasks/${COMPAT_ENCODED_URL_A}/stop?disable=true)"
assert_json "$DISABLE_A_RESP" "obj.get('item', {}).get('enabled') is False" "disable=true did not disable task"
assert_url_config "any(line.lstrip().startswith('#') and '${COMPAT_URL_A}' in line for line in lines)" "URL_config.ini missing disabled # marker"

ENABLE_A_RESP="$(api POST /api/v1/tasks/${COMPAT_ENCODED_URL_A}/start)"
assert_json "$ENABLE_A_RESP" "obj.get('item', {}).get('enabled') is True" "start did not re-enable task"
assert_url_config "not any(line.lstrip().startswith('#') and '${COMPAT_URL_A}' in line for line in lines)" "URL_config.ini still has disabled # marker after start"

echo "[STEP] Functional regression: task CRUD"
CREATE_RESP="$(api POST /api/v1/tasks "{\"url\":\"${CRUD_URL}\",\"quality\":\"原画\",\"anchor_name\":\"phase5-created\"}")"
assert_json "$CREATE_RESP" "obj.get('item', {}).get('url') == '${CRUD_URL}'" "create task failed"

UPDATE_RESP="$(api PUT /api/v1/tasks/${CRUD_ENCODED_URL} "{\"quality\":\"高清\",\"anchor_name\":\"phase5-updated\",\"enabled\":true}")"
assert_json "$UPDATE_RESP" "obj.get('item', {}).get('quality') == '高清' and obj.get('item', {}).get('anchor_name') == 'phase5-updated'" "update task failed"

LIST_RESP="$(api GET /api/v1/tasks)"
assert_json "$LIST_RESP" "any(item.get('url') == '${CRUD_URL}' and item.get('quality') == '高清' for item in obj.get('items', []))" "list task missing CRUD item"

echo "[STEP] Functional regression: start/stop and exception recovery"
START_RESP="$(api POST /api/v1/tasks/${CRUD_ENCODED_URL}/start)"
assert_json "$START_RESP" "obj.get('record_started') is False and 'unsupported platform' in str(obj.get('message', '')).lower()" "unsupported platform recovery check failed"
assert_json "$START_RESP" "obj.get('item', {}).get('enabled') is True" "task should remain enabled after unsupported start"

STOP_RESP="$(api POST /api/v1/tasks/${CRUD_ENCODED_URL}/stop?disable=false)"
assert_json "$STOP_RESP" "obj.get('item', {}).get('enabled') is True" "stop disable=false changed enabled unexpectedly"

DISABLE_RESP="$(api POST /api/v1/tasks/${CRUD_ENCODED_URL}/stop?disable=true)"
assert_json "$DISABLE_RESP" "obj.get('item', {}).get('enabled') is False" "stop disable=true failed"

HEALTH_RESP="$(api GET /health)"
assert_json "$HEALTH_RESP" "obj.get('status') == 'ok'" "service health check failed after unsupported start"

DASHBOARD_RESP="$(api GET /api/v1/dashboard?platform=other)"
assert_json "$DASHBOARD_RESP" "isinstance(obj.get('summary'), dict) and isinstance(obj.get('by_state'), dict) and isinstance(obj.get('items'), list)" "dashboard response schema mismatch"

DELETE_RESP="$(api DELETE /api/v1/tasks/${CRUD_ENCODED_URL})"
assert_json "$DELETE_RESP" "obj.get('deleted') is True" "delete task failed"

FINAL_LIST_RESP="$(api GET /api/v1/tasks)"
assert_json "$FINAL_LIST_RESP" "not any(item.get('url') == '${CRUD_URL}' for item in obj.get('items', []))" "CRUD task still exists after delete"

echo "[STEP] Deployment regression: restart recovery"
dc restart app
wait_health
POST_RESTART_RESP="$(api GET /api/v1/tasks)"
assert_json "$POST_RESTART_RESP" "any(item.get('url') == '${COMPAT_URL_A}' and item.get('enabled') is True for item in obj.get('items', []))" "enabled task not recovered after restart"
assert_json "$POST_RESTART_RESP" "any(item.get('url') == '${COMPAT_URL_D}' and item.get('enabled') is False for item in obj.get('items', []))" "disabled task not recovered after restart"
assert_json "$POST_RESTART_RESP" "any(item.get('url') == '${COMPAT_URL_E}' and item.get('enabled') is False for item in obj.get('items', []))" "disabled single-url task not recovered after restart"

echo "[STEP] Deployment regression: graceful stop"
dc stop -t 35 app
SHUTDOWN_LOGS="$(dc logs --no-color app 2>/dev/null || true)"
if [[ "$SHUTDOWN_LOGS" != *"runtime shutdown requested="* && "$SHUTDOWN_LOGS" != *"Application shutdown complete."* ]]; then
  echo "[ERROR] shutdown log marker not found"
  echo "[DEBUG] Last logs:"
  echo "$SHUTDOWN_LOGS" | tail -n 80
  exit 1
fi

dc up -d app
wait_health
