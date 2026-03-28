# Phase 4 Acceptance Baseline

This baseline validates:

1. Container starts with Web entrypoint.
2. Task CRUD works via API.
3. Task start and stop behavior works with disable=true/false.
4. Container graceful shutdown triggers runtime cleanup.
5. Container restart restores task state from URL_config.ini.
6. Optional: manual start enters recording state when a real live URL is provided.

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

To include end-to-end recording assertion (recommended on cloud host with ffmpeg and a live room):

1. export LIVE_TEST_URL='https://live.douyin.com/904715492544'
2. export LIVE_TEST_QUALITY='原画'  # optional, default 原画
3. export LIVE_TEST_TIMEOUT=120     # optional, wait seconds for recording state
4. ./scripts/phase4_baseline.sh

## Pass Criteria

- Script exits with code 0.
- Final line contains: [PASS] Phase 4 baseline completed successfully
- If LIVE_TEST_URL is set, script must also pass live task assertions: `record_started=true`, `recording_status=recording`, and `started_at` non-empty.

## Notes

- The script creates one temporary task and deletes it at the end.
- If LIVE_TEST_URL is set, the script creates and cleans one extra live-check task.
- The script asserts disabled-task persistence by checking config/URL_config.ini.
- The script checks graceful shutdown via app log marker: runtime shutdown requested=
