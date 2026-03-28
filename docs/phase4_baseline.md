# Phase 4 Acceptance Baseline

This baseline validates:

1. Container starts with Web entrypoint.
2. Task CRUD works via API.
3. Task start and stop behavior works with disable=true/false.
4. Container graceful shutdown triggers runtime cleanup.
5. Container restart restores task state from URL_config.ini.

## Prerequisites

- Linux host with Docker Engine and Docker Compose plugin.
- Repository checked out on host.
- Current directory is repository root.

## Run

If image naming conflicts on your server, set a custom image name first:

1. export DOUYIN_RECORDER_IMAGE=your-registry-or-local-name:phase4

Then run baseline:

1. chmod +x scripts/phase4_baseline.sh
2. ./scripts/phase4_baseline.sh

## Pass Criteria

- Script exits with code 0.
- Final line contains: [PASS] Phase 4 baseline completed successfully

## Notes

- The script creates one temporary task and deletes it at the end.
- The script asserts disabled-task persistence by checking config/URL_config.ini.
- The script checks graceful shutdown via app log marker: runtime shutdown requested=
