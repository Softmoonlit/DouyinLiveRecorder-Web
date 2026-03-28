from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

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
        return [self._to_task_view(task) for task in tasks]

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
        by_platform: dict[str, int] = {}
        for task in tasks:
            platform = str(task.get("platform") or "unknown")
            by_platform[platform] = by_platform.get(platform, 0) + 1

        return {
            **asdict(summary),
            "by_platform": by_platform,
        }

    def get_dashboard(self, platform: str | None = None) -> dict:
        tasks = self.list_tasks()
        if platform:
            target = platform.strip().lower()
            tasks = [task for task in tasks if str(task.get("platform", "")).lower() == target]

        by_state: dict[str, int] = {}
        for task in tasks:
            state = str(task.get("state") or "unknown")
            by_state[state] = by_state.get(state, 0) + 1

        return {
            "summary": self.get_summary(),
            "by_state": by_state,
            "items": tasks,
        }

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
            return self._get_task_view(saved.task_id)

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

            return self._get_task_view(updated.task_id)

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            deleted = self._repo.delete_task(task_id, default_quality=self._default_quality)
            if deleted:
                if self._state.get_task(task_id) is not None:
                    self._state.stop_task(task_id, disable=True)
                self._state.remove_task(task_id)
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
            return self._get_task_view(task_id)

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
            return self._get_task_view(task_id)

    def shutdown(self, *, timeout: float = 10.0) -> dict[str, int]:
        """Stop all enabled runtime tasks during process shutdown."""
        with self._lock:
            snapshot = self._state.get_snapshot()
            active_ids = [task_id for task_id, task in snapshot.items() if bool(task.get("enabled"))]

        stopped = 0
        failed = 0
        for task_id in active_ids:
            try:
                self._state.stop_task(task_id=task_id, timeout=timeout, disable=False)
                stopped += 1
            except Exception:
                failed += 1

        return {
            "requested": len(active_ids),
            "stopped": stopped,
            "failed": failed,
        }

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

    def _get_task_view(self, task_id: str) -> dict | None:
        snapshot = self._state.get_snapshot().get(task_id)
        if snapshot is None:
            return None
        return self._to_task_view(snapshot)

    def _to_task_view(self, task: dict) -> dict:
        state = str(task.get("state") or "offline")
        enabled = bool(task.get("enabled", False))
        platform = self._infer_platform(str(task.get("url") or ""))
        live_status = self._to_live_status(state, enabled)
        recording_status = self._to_recording_status(state, enabled)

        return {
            **task,
            "platform": platform,
            "live_status": live_status,
            "recording_status": recording_status,
            "started_at": task.get("started_recording_at"),
            "error_message": task.get("last_error") or "",
        }

    @staticmethod
    def _to_live_status(state: str, enabled: bool) -> str:
        if not enabled:
            return "disabled"
        if state in {"recording", "live_not_recording", "stopping"}:
            return "live"
        if state in {"monitoring", "offline"}:
            return "not_live"
        return "unknown"

    @staticmethod
    def _to_recording_status(state: str, enabled: bool) -> str:
        if not enabled:
            return "disabled"
        if state == "recording":
            return "recording"
        if state == "stopping":
            return "stopping"
        if state == "failed":
            return "failed"
        return "idle"

    @staticmethod
    def _infer_platform(url: str) -> str:
        host = urlparse(url).netloc.lower()
        if not host:
            return "unknown"

        platform_map = {
            "douyin": ("douyin.com",),
            "kuaishou": ("kuaishou.com",),
            "huya": ("huya.com",),
            "douyu": ("douyu.com",),
            "bilibili": ("bilibili.com",),
            "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
            "tiktok": ("tiktok.com",),
            "youtube": ("youtube.com", "youtu.be"),
            "twitch": ("twitch.tv",),
            "shopee": ("shopee.", "shp.ee"),
            "weibo": ("weibo.com",),
            "yy": ("yy.com",),
        }

        for name, keywords in platform_map.items():
            if any(keyword in host for keyword in keywords):
                return name
        return "other"
