from __future__ import annotations

import logging
from pathlib import Path
from threading import Event, Thread
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.runtime import FfmpegRecordingService, LiveStatusProbe, RuntimeApiManager


BASE_DIR = Path(__file__).resolve().parent
URL_CONFIG_PATH = BASE_DIR / "config" / "URL_config.ini"
CONFIG_PATH = BASE_DIR / "config" / "config.ini"
DOWNLOADS_PATH = BASE_DIR / "downloads"
INDEX_FILE = BASE_DIR / "index.html"
PROBE_INTERVAL_SECONDS = 8.0


app = FastAPI(title="DouyinLiveRecorder API", version="0.1.0")
manager = RuntimeApiManager(URL_CONFIG_PATH)
probe_service = LiveStatusProbe(CONFIG_PATH)
recorder_service = FfmpegRecordingService(CONFIG_PATH, default_download_root=DOWNLOADS_PATH)
probe_stop_event = Event()
probe_thread: Thread | None = None
logger = logging.getLogger(__name__)


def _normalize_task_id(task_id: str) -> str:
    value = unquote(task_id).strip()
    if value.startswith("https:/") and not value.startswith("https://"):
        return value.replace("https:/", "https://", 1)
    if value.startswith("http:/") and not value.startswith("http://"):
        return value.replace("http:/", "http://", 1)
    return value


class TaskCreateRequest(BaseModel):
    url: str = Field(..., min_length=1)
    quality: str = Field(default="原画")
    anchor_name: str = Field(default="")


class TaskUpdateRequest(BaseModel):
    url: str | None = None
    quality: str | None = None
    anchor_name: str | None = None
    enabled: bool | None = None


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
    for item in manager.list_tasks():
        _probe_task_state(item)


def _watch_recording_process(task_id: str, process) -> None:
    try:
        return_code = process.wait()
    except Exception as exc:  # pragma: no cover - subprocess path
        logger.exception("recording watcher failed for %s", task_id)
        manager.mark_task_failed(task_id, f"recording watcher failed: {exc}")
        manager.complete_recording_process(task_id, return_code=1)
        return

    manager.complete_recording_process(task_id, return_code=return_code)


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
        args=(task_id, start_result.process),
        name=f"recording-watch-{task_id[:24]}",
        daemon=True,
    )
    watcher.start()

    return manager.get_task(task_id), True, start_result.output_file


def _probe_loop() -> None:
    while not probe_stop_event.wait(PROBE_INTERVAL_SECONDS):
        try:
            _run_probe_cycle()
        except Exception:  # pragma: no cover - background runtime path
            logger.exception("live probe cycle failed")


@app.on_event("startup")
def on_startup() -> None:
    global probe_thread
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
    items = manager.list_tasks()
    if platform:
        target = platform.strip().lower()
        items = [item for item in items if str(item.get("platform", "")).lower() == target]
    return {"items": items}


@app.post("/api/v1/tasks")
def create_task(payload: TaskCreateRequest) -> dict:
    item = manager.create_task(
        url=payload.url,
        quality=payload.quality,
        anchor_name=payload.anchor_name,
    )
    item = _probe_task_state(item)
    return {"item": item}


@app.put("/api/v1/tasks/{task_id:path}")
def update_task(task_id: str, payload: TaskUpdateRequest) -> dict:
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
    return manager.get_summary()


@app.get("/api/v1/dashboard")
def get_dashboard(platform: str | None = Query(default=None)) -> dict:
    return manager.get_dashboard(platform=platform)


if INDEX_FILE.exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="index file not found")
    return FileResponse(INDEX_FILE)
