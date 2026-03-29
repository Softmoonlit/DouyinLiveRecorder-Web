# Phase 6 Config Validation

This script validates Phase 6 first-batch config.ini adaptation behavior in the Web runtime.

Coverage:

1. Config snapshot endpoint schema (`/api/v1/config/snapshot`).
2. Config reload endpoint behavior (`/api/v1/config/reload`).
3. Default quality application when task creation omits `quality`.
4. Invalid config fallback and warning emission.
5. Sensitive value masking in config snapshot output.
6. Optional live-room boundary check for restart-required recording parameter changes.

## Prerequisites

- Linux cloud server with Docker Engine and Docker Compose plugin.
- Repository checked out on server.
- Current directory is repository root.

## Run

1. `chmod +x scripts/phase6_config_validation.sh`
2. `./scripts/phase6_config_validation.sh`

Optional strict boundary check (requires a real live room URL):

1. `export LIVE_TEST_URL='https://live.douyin.com/904715492544'`
2. `export LIVE_TEST_QUALITY='原画'`
3. `./scripts/phase6_config_validation.sh`

## Pass Criteria

- Script exits with code `0`.
- Final line contains: `[PASS] Phase 6 config validation completed successfully`.

## Notes

- The script backs up and restores both `config/config.ini` and `config/URL_config.ini` automatically.
- If `LIVE_TEST_URL` is not provided, the live restart-boundary check is skipped and all deterministic checks still run.
- The script keeps the container running after completion for manual verification.
