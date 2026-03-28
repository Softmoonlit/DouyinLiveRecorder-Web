from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.runtime import RuntimeApiManager


BASE_DIR = Path(__file__).resolve().parent
URL_CONFIG_PATH = BASE_DIR / "config" / "URL_config.ini"
INDEX_FILE = BASE_DIR / "index.html"


app = FastAPI(title="DouyinLiveRecorder API", version="0.1.0")
manager = RuntimeApiManager(URL_CONFIG_PATH)
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


@app.on_event("startup")
def on_startup() -> None:
    manager.bootstrap()


@app.on_event("shutdown")
def on_shutdown() -> None:
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
    return {"item": item}


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
