# Phase 5 Regression Baseline

This baseline validates:

1. Compatibility regression: legacy `config/URL_config.ini` formats are parsed correctly and `#` disable semantics are preserved.
2. Functional regression: task CRUD, start/stop, unsupported-platform exception recovery, and dashboard schema are stable.
3. Deployment regression: container startup, restart recovery, and graceful shutdown remain healthy.

## Prerequisites

- Linux host with Docker Engine and Docker Compose plugin.
- Repository checked out on host.
- Current directory is repository root.

## Run

If image naming conflicts on your server, set a custom image name first:

1. `export DOUYIN_RECORDER_IMAGE=your-registry-or-local-name:phase5`

Then run baseline:

1. `chmod +x scripts/phase5_regression.sh`
2. `./scripts/phase5_regression.sh`

## Pass Criteria

- Script exits with code `0`.
- Final line contains: `[PASS] Phase 5 regression completed successfully`.
- During execution, all compatibility/functional/deployment assertions pass.

## Notes

- The script temporarily rewrites `config/URL_config.ini` with legacy-format fixtures and restores the original file on exit (success or failure).
- The script keeps the `app` container running at the end for manual verification.
- The unsupported-platform recovery assertion uses `https://example.com/...` URLs to avoid environment-specific live-stream dependencies.