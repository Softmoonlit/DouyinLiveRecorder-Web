#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "[ERROR] This script must be run with bash, for example: bash scripts/phase6_config_validation.sh"
  exit 1
fi

SCRIPT_NAME="$(basename "$0")"

log() {
  local now
  now="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$now] $*"
}

on_error() {
  local exit_code=$?
  local line_no=${BASH_LINENO[0]:-unknown}
  local cmd=${BASH_COMMAND:-unknown}
  echo "[ERROR] ${SCRIPT_NAME} failed at line ${line_no}: ${cmd} (exit=${exit_code})"
}

trap on_error ERR

if [[ "${DEBUG:-0}" == "1" ]]; then
  set -x
fi

log "Starting ${SCRIPT_NAME}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
log "Working directory: $(pwd)"

if [[ "${DOCKER_SUDO:-0}" == "1" ]]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "[ERROR] DOCKER_SUDO=1 is set but sudo is not available"
    exit 1
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    DC=(sudo docker-compose)
  else
    DC=(sudo docker compose)
  fi
else
  if command -v docker-compose >/dev/null 2>&1; then
    DC=(docker-compose)
  else
    DC=(docker compose)
  fi
fi
log "Using compose command: ${DC[*]}"

dc() {
  "${DC[@]}" "$@"
}

for cmd in docker curl python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Missing command: $cmd"
    exit 1
  fi
done

if ! "${DC[@]}" version >/dev/null 2>&1; then
  echo "[ERROR] Docker/Compose is not accessible for current user"
  echo "[HINT] If this is a docker.sock permission issue, run one of these:"
  echo "[HINT]   1) sudo usermod -aG docker \$USER && newgrp docker"
  echo "[HINT]   2) DOCKER_SUDO=1 bash scripts/phase6_config_validation.sh"
  exit 1
fi

mkdir -p config logs backup_config downloads
if [[ ! -f config/config.ini ]]; then
  echo "[ERROR] Missing config/config.ini"
  exit 1
fi
if [[ ! -f config/URL_config.ini ]]; then
  touch config/URL_config.ini
fi

ORIGINAL_CONFIG="$(mktemp)"
ORIGINAL_URL_CONFIG="$(mktemp)"
cp config/config.ini "$ORIGINAL_CONFIG"
cp config/URL_config.ini "$ORIGINAL_URL_CONFIG"

cleanup() {
  local exit_code=$?

  if [[ -f "$ORIGINAL_CONFIG" ]]; then
    cp "$ORIGINAL_CONFIG" config/config.ini || true
    rm -f "$ORIGINAL_CONFIG" || true
  fi
  if [[ -f "$ORIGINAL_URL_CONFIG" ]]; then
    cp "$ORIGINAL_URL_CONFIG" config/URL_config.ini || true
    rm -f "$ORIGINAL_URL_CONFIG" || true
  fi

  if [[ $exit_code -eq 0 ]]; then
    echo "[PASS] Phase 6 config validation completed successfully"
  else
    echo "[FAIL] Phase 6 config validation failed"
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

set_config_value() {
  local section="$1"
  local key="$2"
  local value="$3"

  CFG_PATH="config/config.ini" CFG_SECTION="$section" CFG_KEY="$key" CFG_VALUE="$value" python3 - <<'PY'
import configparser
import os
from pathlib import Path

path = Path(os.environ["CFG_PATH"])
section = os.environ["CFG_SECTION"]
key = os.environ["CFG_KEY"]
value = os.environ["CFG_VALUE"]

parser = configparser.RawConfigParser()
parser.read(path, encoding="utf-8-sig")
if not parser.has_section(section):
    parser.add_section(section)
parser.set(section, key, value)

with open(path, "w", encoding="utf-8-sig") as f:
    parser.write(f)
PY
}

encode_url() {
  local raw_url="$1"
  TEST_URL="$raw_url" python3 - <<'PY'
import os
import urllib.parse

print(urllib.parse.quote(os.environ["TEST_URL"], safe=""))
PY
}

delete_task_if_exists() {
  local raw_url="$1"
  local encoded
  encoded="$(encode_url "$raw_url")"
  curl -fsS -X DELETE "http://127.0.0.1:8000/api/v1/tasks/${encoded}" >/dev/null 2>&1 || true
}

TEST_SUFFIX="$(date +%s)"
TASK_URL_A="https://example.com/phase6-config-a-${TEST_SUFFIX}"
TASK_URL_B="https://example.com/phase6-config-b-${TEST_SUFFIX}"

echo "[INFO] Phase 6 config validation started"

echo "[STEP] Build and start container"
dc up -d --build
wait_health

echo "[STEP] Reset URL task file"
: > config/URL_config.ini

# Ensure clean task state from previous runs.
delete_task_if_exists "$TASK_URL_A"
delete_task_if_exists "$TASK_URL_B"

echo "[STEP] Validate config snapshot endpoint schema"
SNAPSHOT_RESP="$(api GET /api/v1/config/snapshot)"
assert_json "$SNAPSHOT_RESP" "set(['config_path', 'last_reload', 'values']).issubset(set(obj.keys()))" "config snapshot schema mismatch"
assert_json "$SNAPSHOT_RESP" "isinstance(obj.get('values', {}).get('cookies', {}), dict)" "config snapshot cookies field missing"

echo "[STEP] Validate default quality applies when task quality is omitted"
set_config_value "录制设置" "原画|超清|高清|标清|流畅" "高清"
set_config_value "录制设置" "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频" "ts"
RELOAD_RESP="$(api POST /api/v1/config/reload)"
assert_json "$RELOAD_RESP" "obj.get('last_reload', {}).get('success') is True" "config reload failed"

CREATE_A_RESP="$(api POST /api/v1/tasks "{\"url\":\"${TASK_URL_A}\",\"anchor_name\":\"phase6-default-quality\"}")"
assert_json "$CREATE_A_RESP" "obj.get('item', {}).get('quality') == '高清'" "default quality was not applied"

echo "[STEP] Validate invalid config fallback and warning generation"
set_config_value "录制设置" "原画|超清|高清|标清|流畅" "invalid_quality"
set_config_value "录制设置" "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频" "invalid_format"
set_config_value "录制设置" "分段录制是否开启" "invalid_bool"
set_config_value "录制设置" "视频分段时间(秒)" "invalid_int"
set_config_value "录制设置" "循环时间(秒)" "0"
INVALID_RELOAD_RESP="$(api POST /api/v1/config/reload)"
assert_json "$INVALID_RELOAD_RESP" "obj.get('last_reload', {}).get('success') is True" "reload should succeed with fallback"
assert_json "$INVALID_RELOAD_RESP" "len(obj.get('last_reload', {}).get('warnings', [])) >= 1" "invalid config did not produce warnings"
assert_json "$INVALID_RELOAD_RESP" "obj.get('values', {}).get('default_quality') == '原画'" "invalid default quality did not fallback"
assert_json "$INVALID_RELOAD_RESP" "obj.get('values', {}).get('save_format') == 'TS'" "invalid save format did not fallback"
assert_json "$INVALID_RELOAD_RESP" "obj.get('values', {}).get('split_time_seconds') == 1800" "invalid split time did not fallback"
assert_json "$INVALID_RELOAD_RESP" "float(obj.get('values', {}).get('probe_interval_seconds')) == 2.0" "probe interval clamp failed"

echo "[STEP] Validate sensitive fields are masked in config snapshot"
set_config_value "录制设置" "代理地址" "http://12.34.56.78:9000"
set_config_value "Cookie" "抖音cookie" "abcdef1234567890"
MASK_RESP="$(api POST /api/v1/config/reload)"
assert_json "$MASK_RESP" "obj.get('values', {}).get('proxy_addr') != 'http://12.34.56.78:9000'" "proxy address is not masked"
assert_json "$MASK_RESP" "'***' in str(obj.get('values', {}).get('proxy_addr', ''))" "proxy address mask format mismatch"
assert_json "$MASK_RESP" "obj.get('values', {}).get('cookies', {}).get('douyin') != 'abcdef1234567890'" "cookie is not masked"

if [[ -n "${LIVE_TEST_URL:-}" ]]; then
  echo "[STEP] Optional: validate running-task restart boundary with live URL"
  LIVE_QUALITY="${LIVE_TEST_QUALITY:-原画}"
  LIVE_URL="$LIVE_TEST_URL"
  LIVE_ENCODED_URL="$(encode_url "$LIVE_URL")"

  set_config_value "录制设置" "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频" "ts"
  api POST "/api/v1/config/reload" >/dev/null

  LIVE_CREATE_RESP="$(api POST /api/v1/tasks "{\"url\":\"${LIVE_URL}\",\"quality\":\"${LIVE_QUALITY}\",\"anchor_name\":\"phase6-live\"}")"
  assert_json "$LIVE_CREATE_RESP" "obj.get('item', {}).get('url') == '${LIVE_URL}'" "live task creation failed"

  LIVE_START_TS="$(api POST /api/v1/tasks/${LIVE_ENCODED_URL}/start)"
  assert_json "$LIVE_START_TS" "obj.get('record_started') is True" "live task did not start recording with ts"
  assert_json "$LIVE_START_TS" "str(obj.get('message', '')).endswith('.ts') or str(obj.get('message', '')).endswith('_%03d.ts')" "ts output extension check failed"

  set_config_value "录制设置" "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频" "mp4"
  api POST "/api/v1/config/reload" >/dev/null

  api POST "/api/v1/tasks/${LIVE_ENCODED_URL}/stop?disable=false" >/dev/null
  sleep 2

  LIVE_START_MP4="$(api POST /api/v1/tasks/${LIVE_ENCODED_URL}/start)"
  assert_json "$LIVE_START_MP4" "obj.get('record_started') is True" "live task did not restart recording with mp4"
  assert_json "$LIVE_START_MP4" "str(obj.get('message', '')).endswith('.mp4') or str(obj.get('message', '')).endswith('_%03d.mp4')" "mp4 output extension check failed"

  api POST "/api/v1/tasks/${LIVE_ENCODED_URL}/stop?disable=true" >/dev/null || true
  api DELETE "/api/v1/tasks/${LIVE_ENCODED_URL}" >/dev/null || true
else
  echo "[INFO] LIVE_TEST_URL not set, skip optional running-task restart boundary check"
fi

echo "[STEP] Cleanup test tasks"
delete_task_if_exists "$TASK_URL_A"
delete_task_if_exists "$TASK_URL_B"

echo "[STEP] Restore default quality for next run and reload"
set_config_value "录制设置" "原画|超清|高清|标清|流畅" "原画"
api POST "/api/v1/config/reload" >/dev/null
