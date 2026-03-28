from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from src import utils

from .service import RuntimeStateService
from .url_config_repository import UrlConfigRepository, UrlConfigTask


@dataclass
class RuntimeSummary:
    total: int
    enabled: int
    disabled: int
    monitoring: int
    live_not_recording: int
    recording: int
    stopping: int
    failed: int
    offline: int


class RuntimeApiManager:
    """Phase 2 state manager with transitional dual-write to URL_config.ini."""

    def __init__(
        self,
        url_config_path: str | Path,
        *,
        default_quality: str = "原画",
        runtime_state_service: RuntimeStateService | None = None,
    ) -> None:
        self._default_quality = default_quality
        self._repo = UrlConfigRepository(url_config_path)
        self._state = runtime_state_service or RuntimeStateService()
        self._lock = threading.RLock()
        self._url_config_md5 = ""

    def bootstrap(self) -> None:
        self._refresh_from_file(force=True)

    def refresh_if_changed(self) -> bool:
        return self._refresh_from_file(force=False)

    def list_tasks(self) -> list[dict]:
        self.refresh_if_changed()
        snapshot = self._state.get_snapshot()
        tasks = sorted(snapshot.values(), key=lambda x: x.get("url", ""))
        return tasks

    def get_summary(self) -> dict:
        tasks = self.list_tasks()
        summary = RuntimeSummary(
            total=len(tasks),
            enabled=sum(1 for task in tasks if task.get("enabled")),
            disabled=sum(1 for task in tasks if not task.get("enabled")),
            monitoring=sum(1 for task in tasks if task.get("state") == "monitoring"),
            live_not_recording=sum(1 for task in tasks if task.get("state") == "live_not_recording"),
            recording=sum(1 for task in tasks if task.get("state") == "recording"),
            stopping=sum(1 for task in tasks if task.get("state") == "stopping"),
            failed=sum(1 for task in tasks if task.get("state") == "failed"),
            offline=sum(1 for task in tasks if task.get("state") == "offline"),
        )
        return asdict(summary)

    def create_task(self, *, url: str, quality: str | None = None, anchor_name: str = "") -> dict:
        with self._lock:
            quality_value = quality or self._default_quality
            task = UrlConfigTask(
                quality=quality_value,
                url=url,
                anchor_name=anchor_name,
                enabled=True,
            )
            saved = self._repo.upsert_task(task, default_quality=self._default_quality)
            self._state.upsert_task(
                saved.task_id,
                url=saved.url,
                quality=saved.quality,
                anchor_name=saved.anchor_name,
            )
            return self._state.get_snapshot()[saved.task_id]

    def update_task(
        self,
        task_id: str,
        *,
        quality: str | None = None,
        anchor_name: str | None = None,
        url: str | None = None,
        enabled: bool | None = None,
    ) -> dict | None:
        with self._lock:
            updated = self._repo.update_task(
                task_id,
                quality=quality,
                anchor_name=anchor_name,
                new_url=url,
                enabled=enabled,
                default_quality=self._default_quality,
            )
            if updated is None:
                return None

            if task_id != updated.task_id:
                self._state.disable_task(task_id)

            if updated.enabled:
                self._state.upsert_task(
                    updated.task_id,
                    url=updated.url,
                    quality=updated.quality,
                    anchor_name=updated.anchor_name,
                )
                self._state.mark_monitoring(updated.task_id)
            else:
                self._state.disable_task(updated.task_id)

            return self._state.get_snapshot().get(updated.task_id)

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            deleted = self._repo.delete_task(task_id, default_quality=self._default_quality)
            if deleted:
                self._state.stop_task(task_id, disable=True)
            return deleted

    def start_task(self, task_id: str) -> dict | None:
        with self._lock:
            enabled = self._repo.set_task_enabled(task_id, True, default_quality=self._default_quality)
            if not enabled:
                return None
            current = self._repo.update_task(task_id, default_quality=self._default_quality)
            if current is None:
                return None
            self._state.upsert_task(
                task_id,
                url=current.url,
                quality=current.quality,
                anchor_name=current.anchor_name,
            )
            self._state.mark_monitoring(task_id)
            return self._state.get_snapshot().get(task_id)

    def stop_task(self, task_id: str, *, disable: bool = False) -> dict | None:
        with self._lock:
            exists = self._state.get_task(task_id) is not None
            if not exists:
                current = self._repo.update_task(task_id, default_quality=self._default_quality)
                if current is None:
                    return None
                self._state.upsert_task(
                    task_id,
                    url=current.url,
                    quality=current.quality,
                    anchor_name=current.anchor_name,
                )

            self._state.stop_task(task_id=task_id, disable=disable)
            if disable:
                self._repo.set_task_enabled(task_id, False, default_quality=self._default_quality)
            else:
                self._repo.set_task_enabled(task_id, True, default_quality=self._default_quality)
            return self._state.get_snapshot().get(task_id)

    def _refresh_from_file(self, *, force: bool) -> bool:
        with self._lock:
            path = self._repo.file_path
            self._repo.ensure_file()
            current_md5 = utils.check_md5(path) if path.exists() else ""
            if not force and current_md5 == self._url_config_md5:
                return False

            tasks = self._repo.load_tasks(default_quality=self._default_quality)
            enabled_tuples = [(task.quality, task.url, task.anchor_name) for task in tasks if task.enabled]
            disabled_urls = [task.url for task in tasks if not task.enabled]
            self._state.reload_from_url_config(enabled_tuples, disabled_urls)
            self._url_config_md5 = current_md5
            return True
