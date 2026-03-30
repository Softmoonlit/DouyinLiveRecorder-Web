#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "[ERROR] This script must be run with bash, for example: bash scripts/phase6_network_validation.sh"
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
  echo "[HINT]   2) DOCKER_SUDO=1 bash scripts/phase6_network_validation.sh"
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
    echo "[PASS] Phase 6.2 network stability validation completed successfully"
  else
    echo "[FAIL] Phase 6.2 network stability validation failed"
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
TASK_URL="http://example.com/phase62-network-${TEST_SUFFIX}.m3u8"

log "Phase 6.2 network stability validation started"

echo "[STEP] Build and start container"
dc up -d --build
wait_health

echo "[STEP] Reset URL task file"
: > config/URL_config.ini

delete_task_if_exists "$TASK_URL"

echo "[STEP] Validate snapshot contains phase 6.2 fields"
SNAPSHOT_RESP="$(api GET /api/v1/config/snapshot)"
assert_json "$SNAPSHOT_RESP" "'max_request_workers' in obj.get('values', {})" "missing max_request_workers in snapshot"
assert_json "$SNAPSHOT_RESP" "'disk_space_limit_gb' in obj.get('values', {})" "missing disk_space_limit_gb in snapshot"
assert_json "$SNAPSHOT_RESP" "'force_https_recording' in obj.get('values', {})" "missing force_https_recording in snapshot"

echo "[STEP] Validate proxy switch and proxy address masking"
set_config_value "录制设置" "是否使用代理ip(是/否)" "否"
set_config_value "录制设置" "代理地址" "127.0.0.1:7890"
PROXY_OFF_RESP="$(api POST /api/v1/config/reload)"
assert_json "$PROXY_OFF_RESP" "obj.get('values', {}).get('use_proxy') is False" "use_proxy off did not take effect"
assert_json "$PROXY_OFF_RESP" "obj.get('values', {}).get('proxy_addr') != '127.0.0.1:7890'" "proxy address is not masked"

set_config_value "录制设置" "是否使用代理ip(是/否)" "是"
PROXY_ON_RESP="$(api POST /api/v1/config/reload)"
assert_json "$PROXY_ON_RESP" "obj.get('values', {}).get('use_proxy') is True" "use_proxy on did not take effect"

echo "[STEP] Validate max worker parsing and clamp"
set_config_value "录制设置" "同一时间访问网络的线程数" "0"
WORKER_CLAMP_RESP="$(api POST /api/v1/config/reload)"
assert_json "$WORKER_CLAMP_RESP" "int(obj.get('values', {}).get('max_request_workers')) == 1" "max workers clamp failed"

set_config_value "录制设置" "同一时间访问网络的线程数" "11"
WORKER_SET_RESP="$(api POST /api/v1/config/reload)"
assert_json "$WORKER_SET_RESP" "int(obj.get('values', {}).get('max_request_workers')) == 11" "max workers set failed"

echo "[STEP] Validate disk threshold parsing"
set_config_value "录制设置" "录制空间剩余阈值(gb)" "invalid_float"
DISK_FALLBACK_RESP="$(api POST /api/v1/config/reload)"
assert_json "$DISK_FALLBACK_RESP" "float(obj.get('values', {}).get('disk_space_limit_gb')) == 1.0" "disk threshold fallback failed"

set_config_value "录制设置" "录制空间剩余阈值(gb)" "2.5"
DISK_SET_RESP="$(api POST /api/v1/config/reload)"
assert_json "$DISK_SET_RESP" "float(obj.get('values', {}).get('disk_space_limit_gb')) == 2.5" "disk threshold set failed"

echo "[STEP] Validate force HTTPS conversion in recorder"
set_config_value "录制设置" "是否强制启用https录制" "是"
set_config_value "录制设置" "录制空间剩余阈值(gb)" "0"
HTTPS_SIM_RESP="$(dc exec -T app python - <<'PY'
import json
import subprocess
import shutil

from src.runtime import FfmpegRecordingService, LiveProbeResult

captured = {}

class DummyProc:
    def __init__(self, cmd):
        captured["cmd"] = cmd

orig_which = shutil.which
orig_popen = subprocess.Popen

try:
    shutil.which = lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None

    def _fake_popen(cmd, **kwargs):
        return DummyProc(cmd)

    subprocess.Popen = _fake_popen

    service = FfmpegRecordingService("config/config.ini", default_download_root="downloads")
    result = service.start_recording(
        task={"anchor_name": "phase62-https", "platform": "custom"},
        probe_result=LiveProbeResult(
            supported=True,
            is_live=True,
            anchor_name="phase62-https",
            error="",
            record_url="http://example.com/live/phase62.m3u8",
            platform="custom",
            title="",
        ),
    )

    cmd = captured.get("cmd", [])
    input_url = ""
    if "-i" in cmd:
        input_url = cmd[cmd.index("-i") + 1]

    print(json.dumps({"started": result.started, "input_url": input_url}, ensure_ascii=False))
finally:
    shutil.which = orig_which
    subprocess.Popen = orig_popen
PY
)"
assert_json "$HTTPS_SIM_RESP" "obj.get('started') is True" "recorder https simulation did not start"
assert_json "$HTTPS_SIM_RESP" "str(obj.get('input_url', '')).startswith('https://')" "force https conversion failed"

echo "[STEP] Validate live probe applies configured worker count"
PROBE_WORKER_RESP="$(dc exec -T app python - <<'PY'
import json

from src.runtime import LiveStatusProbe, RuntimeConfigService

service = RuntimeConfigService("config/config.ini")
probe = LiveStatusProbe(service)
print(json.dumps({"max_workers": int(getattr(probe, "_max_workers", -1))}, ensure_ascii=False))
PY
)"
assert_json "$PROBE_WORKER_RESP" "int(obj.get('max_workers')) == 11" "live probe did not apply configured worker count"

echo "[STEP] Validate disk threshold blocks new recording start"
set_config_value "录制设置" "录制空间剩余阈值(gb)" "10240"
api POST "/api/v1/config/reload" >/dev/null

CREATE_RESP="$(api POST /api/v1/tasks "{\"url\":\"${TASK_URL}\",\"anchor_name\":\"phase62-disk\"}")"
assert_json "$CREATE_RESP" "obj.get('item', {}).get('url') == '${TASK_URL}'" "task creation failed for disk check"

ENCODED_TASK_URL="$(encode_url "$TASK_URL")"
START_RESP="$(api POST /api/v1/tasks/${ENCODED_TASK_URL}/start)"
assert_json "$START_RESP" "obj.get('record_started') is False" "recording should be blocked by disk threshold"
assert_json "$START_RESP" "'disk free space' in str(obj.get('message', '')).lower()" "disk threshold block message mismatch"

echo "[STEP] Cleanup test task and restore defaults"
delete_task_if_exists "$TASK_URL"
set_config_value "录制设置" "是否使用代理ip(是/否)" "是"
set_config_value "录制设置" "代理地址" ""
set_config_value "录制设置" "同一时间访问网络的线程数" "3"
set_config_value "录制设置" "是否强制启用https录制" "否"
set_config_value "录制设置" "录制空间剩余阈值(gb)" "1.0"
api POST "/api/v1/config/reload" >/dev/null
