from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path
import shutil
from threading import Event, Thread
import time
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.runtime import FfmpegRecordingService, LiveStatusProbe, RuntimeApiManager, RuntimeConfigService


BASE_DIR = Path(__file__).resolve().parent
URL_CONFIG_PATH = BASE_DIR / "config" / "URL_config.ini"
CONFIG_PATH = BASE_DIR / "config" / "config.ini"
DOWNLOADS_PATH = BASE_DIR / "downloads"
INDEX_FILE = BASE_DIR / "index.html"
V2_DIST_DIR = BASE_DIR / "static" / "web-v2"
V2_INDEX_FILE = V2_DIST_DIR / "index.html"
UI_SESSION_STORAGE_KEY = "douyin_live_recorder_ui_version"


def _normalize_ui_version(value: str | None) -> str:
    return str(value or "").strip().lower()


def _parse_allowed_ui_versions() -> tuple[str, ...]:
    raw = os.getenv("DOUYIN_WEB_UI_ALLOWED", "v1,v2")
    values: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        version = _normalize_ui_version(item)
        if not version:
            continue
        if version in seen:
            continue
        seen.add(version)
        values.append(version)

    if not values:
        return ("v1",)
    if "v1" not in seen:
        values.append("v1")
    return tuple(values)


def _resolve_default_ui_version(allowed: tuple[str, ...]) -> str:
    env_default = _normalize_ui_version(os.getenv("DOUYIN_WEB_UI_DEFAULT", "v1"))
    if env_default in allowed:
        return env_default
    if "v1" in allowed:
        return "v1"
    return allowed[0]


UI_ALLOWED_VERSIONS = _parse_allowed_ui_versions()
UI_DEFAULT_VERSION = _resolve_default_ui_version(UI_ALLOWED_VERSIONS)
APP_STARTED_AT = time.time()


app = FastAPI(title="DouyinLiveRecorder API", version="0.1.0")
runtime_config_service = RuntimeConfigService(CONFIG_PATH)
manager = RuntimeApiManager(
    URL_CONFIG_PATH,
    default_quality=runtime_config_service.get_values().default_quality,
)
probe_service = LiveStatusProbe(runtime_config_service)
recorder_service = FfmpegRecordingService(runtime_config_service, default_download_root=DOWNLOADS_PATH)
probe_stop_event = Event()
probe_thread: Thread | None = None
logger = logging.getLogger(__name__)


def _build_runtime_metrics() -> dict[str, Any]:
    sampled_at = int(time.time())
    uptime_seconds = max(0, int(time.time() - APP_STARTED_AT))

    metrics: dict[str, Any] = {
        "uptime": {
            "raw": uptime_seconds,
            "unit": "second",
            "sampled_at": sampled_at,
            "available": True,
        }
    }

    disk_target = DOWNLOADS_PATH if DOWNLOADS_PATH.exists() else BASE_DIR
    try:
        usage = shutil.disk_usage(disk_target)
        total_gib = usage.total / (1024 ** 3)
        used_gib = usage.used / (1024 ** 3)
        free_gib = usage.free / (1024 ** 3)
        usage_ratio = (used_gib / total_gib) if total_gib > 0 else 0.0
        metrics["disk"] = {
            "raw": {
                "used_gib": used_gib,
                "total_gib": total_gib,
                "free_gib": free_gib,
                "usage_ratio": usage_ratio,
            },
            "unit": "GiB",
            "sampled_at": sampled_at,
            "available": True,
        }
    except Exception as exc:  # pragma: no cover
        metrics["disk"] = {
            "raw": None,
            "unit": "GiB",
            "sampled_at": sampled_at,
            "available": False,
            "error": str(exc),
        }

    return metrics


def _build_ui_bootstrap_html() -> str:
    config = {
        "allowed": list(UI_ALLOWED_VERSIONS),
        "default": UI_DEFAULT_VERSION,
        "sessionKey": UI_SESSION_STORAGE_KEY,
    }
    config_json = html.escape(json.dumps(config, ensure_ascii=False))

    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>DouyinLiveRecorder 控制台</title>
    <style>
        body {{
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            font-family: \"IBM Plex Sans SC\", \"Microsoft YaHei\", sans-serif;
            background: linear-gradient(140deg, #081c2f 0%, #0d2f4a 48%, #15365f 100%);
            color: #f5f8ff;
        }}
        .card {{
            width: min(560px, calc(100vw - 32px));
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.22);
            background: rgba(5, 17, 31, 0.62);
            padding: 20px;
            box-sizing: border-box;
            box-shadow: 0 18px 40px rgba(2, 10, 18, 0.36);
        }}
        h1 {{ margin: 0 0 10px; font-size: 22px; }}
        p {{ margin: 0; color: rgba(245, 248, 255, 0.84); line-height: 1.6; }}
        .link {{
            margin-top: 12px;
            display: inline-block;
            color: #9be7de;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class=\"card\">
        <h1>正在进入控制台</h1>
        <p>系统将根据 URL 参数、会话记忆与环境变量自动选择界面版本。</p>
        <noscript><a class=\"link\" href=\"/ui/v1\">当前浏览器禁用脚本，点击进入旧版界面</a></noscript>
    </div>
    <script id=\"ui-config\" type=\"application/json\">{config_json}</script>
    <script>
        (function () {{
            var configEl = document.getElementById('ui-config');
            if (!configEl) {{
                window.location.replace('/ui/v1');
                return;
            }}

            var config = {{ allowed: ['v1'], default: 'v1', sessionKey: 'douyin_live_recorder_ui_version' }};
            try {{
                config = JSON.parse(configEl.textContent || '{}');
            }} catch (e) {{
                window.location.replace('/ui/v1');
                return;
            }}

            var allowedSet = new Set(Array.isArray(config.allowed) ? config.allowed : ['v1']);
            var sessionKey = String(config.sessionKey || 'douyin_live_recorder_ui_version');
            var params = new URLSearchParams(window.location.search);
            var requested = String(params.get('ui') || '').trim().toLowerCase();
            var selected = '';

            if (allowedSet.has(requested)) {{
                selected = requested;
                try {{
                    sessionStorage.setItem(sessionKey, selected);
                }} catch (e) {{
                }}
            }}

            if (!selected) {{
                try {{
                    var remembered = String(sessionStorage.getItem(sessionKey) || '').trim().toLowerCase();
                    if (allowedSet.has(remembered)) {{
                        selected = remembered;
                    }}
                }} catch (e) {{
                }}
            }}

            if (!selected) {{
                var fallback = String(config.default || '').trim().toLowerCase();
                if (allowedSet.has(fallback)) {{
                    selected = fallback;
                }}
            }}

            if (!selected) {{
                selected = allowedSet.has('v1') ? 'v1' : ((Array.isArray(config.allowed) && config.allowed[0]) || 'v1');
            }}

            params.delete('ui');
            var passthrough = params.toString();
            var query = passthrough ? ('?' + passthrough) : '';
            var target = selected === 'v2' ? '/ui/v2' : '/ui/v1';
            window.location.replace(target + query);
        }})();
    </script>
</body>
</html>
"""


def _normalize_task_id(task_id: str) -> str:
    value = unquote(task_id).strip()
    if value.startswith("https:/") and not value.startswith("https://"):
        return value.replace("https:/", "https://", 1)
    if value.startswith("http:/") and not value.startswith("http://"):
        return value.replace("http:/", "http://", 1)
    return value


class TaskCreateRequest(BaseModel):
    url: str = Field(..., min_length=1)
    quality: str | None = Field(default=None)
    anchor_name: str = Field(default="")


class TaskUpdateRequest(BaseModel):
    url: str | None = None
    quality: str | None = None
    anchor_name: str | None = None
    enabled: bool | None = None


class ConfigUpdateRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


def _refresh_runtime_config(*, force: bool = False) -> None:
    result = runtime_config_service.reload_if_needed(force=force)
    manager.set_default_quality(runtime_config_service.get_values().default_quality)

    if not result.success and result.error:
        logger.warning(result.error)
    if result.changed:
        for warning in result.warnings:
            logger.warning("config warning: %s", warning)


def _probe_task_state(task: dict | None) -> dict | None:
    if not task:
        return task

    task_id = str(task.get("task_id") or "").strip()
    task_url = str(task.get("url") or "").strip()
    task_quality = str(task.get("quality") or "原画").strip()
    if not task_id or not task_url or not bool(task.get("enabled", False)):
        return task

    probe_result = probe_service.probe(task_url, task_quality)
    updated = manager.apply_probe_result(
        task_id,
        is_live=probe_result.is_live,
        anchor_name=probe_result.anchor_name,
        error=probe_result.error,
    )
    return updated or task


def _run_probe_cycle() -> None:
    _refresh_runtime_config()
    for item in manager.list_tasks():
        _probe_task_state(item)


def _watch_recording_process(task_id: str, process, output_file: str) -> None:
    try:
        return_code = process.wait()
    except Exception as exc:  # pragma: no cover
        logger.exception("recording watcher failed for %s", task_id)
        manager.mark_task_failed(task_id, f"recording watcher failed: {exc}")
        manager.complete_recording_process(task_id, return_code=1)
        return

    post_process_error = ""
    if return_code == 0:
        ok, output_or_error = recorder_service.finalize_recording(output_file)
        if not ok:
            post_process_error = output_or_error

    manager.complete_recording_process(task_id, return_code=return_code)
    if post_process_error:
        manager.mark_task_failed(task_id, post_process_error)


def _start_recording_if_live(task: dict | None) -> tuple[dict | None, bool, str]:
    if not task:
        return task, False, "task not found"

    task_id = str(task.get("task_id") or "").strip()
    task_url = str(task.get("url") or "").strip()
    task_quality = str(task.get("quality") or "原画").strip()
    if not task_id or not task_url:
        return task, False, "invalid task metadata"

    if str(task.get("recording_status") or "") == "recording":
        return task, False, "task is already recording"

    probe_result = probe_service.probe(task_url, task_quality)
    updated = manager.apply_probe_result(
        task_id,
        is_live=probe_result.is_live,
        anchor_name=probe_result.anchor_name,
        error=probe_result.error,
    )
    current_task = updated or task

    if not probe_result.supported:
        return current_task, False, "unsupported platform for manual recording start"
    if probe_result.error:
        return current_task, False, probe_result.error
    if probe_result.is_live is not True:
        return current_task, False, "room is not live"

    start_result = recorder_service.start_recording(current_task, probe_result)
    if not start_result.started or start_result.process is None:
        failed_task = manager.mark_task_failed(task_id, start_result.message) or current_task
        return failed_task, False, start_result.message

    if not manager.bind_recording_process(task_id, start_result.process):
        try:
            if start_result.process.poll() is None:
                start_result.process.terminate()
        except Exception:
            logger.exception("failed to terminate unbound recording process for %s", task_id)
        failed_task = manager.mark_task_failed(task_id, "bind recording process failed") or current_task
        return failed_task, False, "bind recording process failed"

    watcher = Thread(
        target=_watch_recording_process,
        args=(task_id, start_result.process, start_result.output_file),
        name=f"recording-watch-{task_id[:24]}",
        daemon=True,
    )
    watcher.start()

    return manager.get_task(task_id), True, start_result.output_file


def _probe_loop() -> None:
    while True:
        _refresh_runtime_config()
        probe_interval_seconds = runtime_config_service.get_values().probe_interval_seconds
        if probe_stop_event.wait(probe_interval_seconds):
            break
        try:
            _run_probe_cycle()
        except Exception:  # pragma: no cover
            logger.exception("live probe cycle failed")


@app.on_event("startup")
def on_startup() -> None:
    global probe_thread
    _refresh_runtime_config(force=True)
    manager.bootstrap()
    _run_probe_cycle()
    probe_stop_event.clear()
    probe_thread = Thread(target=_probe_loop, name="live-status-probe", daemon=True)
    probe_thread.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    global probe_thread
    probe_stop_event.set()
    if probe_thread and probe_thread.is_alive():
        probe_thread.join(timeout=3.0)
    probe_thread = None

    result = manager.shutdown(timeout=15.0)
    logger.info(
        "runtime shutdown requested=%s stopped=%s failed=%s",
        result.get("requested", 0),
        result.get("stopped", 0),
        result.get("failed", 0),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/tasks")
def list_tasks(platform: str | None = Query(default=None)) -> dict[str, list[dict]]:
    _refresh_runtime_config()
    items = manager.list_tasks()
    if platform:
        target = platform.strip().lower()
        items = [item for item in items if str(item.get("platform", "")).lower() == target]
    return {"items": items}


@app.post("/api/v1/tasks")
def create_task(payload: TaskCreateRequest) -> dict:
    _refresh_runtime_config()
    item = manager.create_task(
        url=payload.url,
        quality=payload.quality,
        anchor_name=payload.anchor_name,
    )
    item = _probe_task_state(item)
    return {"item": item}


@app.put("/api/v1/tasks/{task_id:path}")
def update_task(task_id: str, payload: TaskUpdateRequest) -> dict:
    _refresh_runtime_config()
    normalized_task_id = _normalize_task_id(task_id)
    item = manager.update_task(
        normalized_task_id,
        url=payload.url,
        quality=payload.quality,
        anchor_name=payload.anchor_name,
        enabled=payload.enabled,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="task not found")
    item = _probe_task_state(item)
    return {"item": item}


@app.delete("/api/v1/tasks/{task_id:path}")
def delete_task(task_id: str) -> dict[str, bool]:
    normalized_task_id = _normalize_task_id(task_id)
    ok = manager.delete_task(normalized_task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task not found")
    return {"deleted": True}


@app.post("/api/v1/tasks/{task_id:path}/start")
def start_task(task_id: str) -> dict:
    _refresh_runtime_config()
    normalized_task_id = _normalize_task_id(task_id)
    item = manager.start_task(normalized_task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="task not found")
    item, record_started, message = _start_recording_if_live(item)
    return {
        "item": item,
        "record_started": record_started,
        "message": message,
    }


@app.post("/api/v1/tasks/{task_id:path}/stop")
def stop_task(task_id: str, disable: bool = Query(default=False)) -> dict:
    normalized_task_id = _normalize_task_id(task_id)
    item = manager.stop_task(normalized_task_id, disable=disable)
    if item is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"item": item}


@app.get("/api/v1/summary")
def get_summary() -> dict:
    _refresh_runtime_config()
    return manager.get_summary()


@app.get("/api/v1/dashboard")
def get_dashboard(platform: str | None = Query(default=None)) -> dict:
    _refresh_runtime_config()
    payload = manager.get_dashboard(platform=platform)
    payload["metrics"] = _build_runtime_metrics()
    return payload


@app.get("/api/v1/ui-version")
def get_ui_version_config() -> dict[str, Any]:
    return {
        "allowed": list(UI_ALLOWED_VERSIONS),
        "default": UI_DEFAULT_VERSION,
        "session_key": UI_SESSION_STORAGE_KEY,
    }


@app.get("/api/v1/config/settings")
def get_config_settings() -> dict:
    _refresh_runtime_config()
    return runtime_config_service.get_settings_payload()


@app.post("/api/v1/config/update-settings")
def update_config_settings(payload: ConfigUpdateRequest) -> dict:
    result = runtime_config_service.update_settings(payload.fields)
    _refresh_runtime_config(force=True)
    return result


@app.get("/api/v1/config/snapshot")
def get_config_snapshot() -> dict:
    _refresh_runtime_config()
    return runtime_config_service.get_snapshot(mask_sensitive=True)


@app.post("/api/v1/config/reload")
def reload_config() -> dict:
    _refresh_runtime_config(force=True)
    return runtime_config_service.get_snapshot(mask_sensitive=True)


if INDEX_FILE.exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(_build_ui_bootstrap_html())


@app.get("/ui/v1")
def index_v1() -> FileResponse:
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="index file not found")
    return FileResponse(INDEX_FILE)


@app.get("/ui/v2")
def index_v2() -> FileResponse:
    if not V2_INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="v2 index file not found, please build frontend assets")
    return FileResponse(V2_INDEX_FILE)
