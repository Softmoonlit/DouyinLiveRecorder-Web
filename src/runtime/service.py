from __future__ import annotations

import signal
import threading
import time
from subprocess import TimeoutExpired

from .models import RuntimeTask, TaskHandle, TaskState


class RuntimeStateService:
    """Thread-safe runtime state registry for monitor/recording tasks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, RuntimeTask] = {}
        self._handles: dict[str, TaskHandle] = {}

    def _get_or_create_task(self, task_id: str, url: str | None = None) -> RuntimeTask:
        if task_id not in self._tasks:
            self._tasks[task_id] = RuntimeTask(task_id=task_id, url=url or task_id)
        elif url:
            self._tasks[task_id].url = url
        return self._tasks[task_id]

    def _touch(self, task: RuntimeTask) -> None:
        task.updated_at = time.time()

    def upsert_task(self, task_id: str, *, url: str, quality: str = "原画", anchor_name: str = "") -> RuntimeTask:
        with self._lock:
            task = self._get_or_create_task(task_id, url)
            task.quality = quality
            task.anchor_name = anchor_name
            if not task.enabled:
                task.enabled = True
            if task.state == TaskState.OFFLINE:
                task.state = TaskState.MONITORING
            self._touch(task)
            return task

    def disable_task(self, task_id: str) -> None:
        with self._lock:
            task = self._get_or_create_task(task_id)
            task.enabled = False
            task.state = TaskState.OFFLINE
            self._touch(task)

    def bind_monitor_thread(self, task_id: str, monitor_thread: threading.Thread | None = None) -> None:
        with self._lock:
            handle = self._handles.setdefault(task_id, TaskHandle())
            handle.monitor_thread = monitor_thread
            handle.reset_stop_flag()

    def bind_process(self, task_id: str, process) -> None:
        with self._lock:
            handle = self._handles.setdefault(task_id, TaskHandle())
            handle.process = process

    def unbind_process(self, task_id: str) -> None:
        with self._lock:
            handle = self._handles.get(task_id)
            if handle:
                handle.process = None

    def should_stop(self, task_id: str) -> bool:
        with self._lock:
            handle = self._handles.get(task_id)
            return bool(handle and handle.should_stop())

    def mark_monitoring(self, task_id: str) -> None:
        with self._lock:
            task = self._get_or_create_task(task_id)
            if task.enabled:
                task.state = TaskState.MONITORING
                self._touch(task)

    def mark_live_not_recording(self, task_id: str) -> None:
        with self._lock:
            task = self._get_or_create_task(task_id)
            if task.enabled:
                task.state = TaskState.LIVE_NOT_RECORDING
                self._touch(task)

    def mark_recording(self, task_id: str) -> None:
        with self._lock:
            task = self._get_or_create_task(task_id)
            if task.enabled:
                task.state = TaskState.RECORDING
                if task.started_recording_at is None:
                    task.started_recording_at = time.time()
                self._touch(task)

    def mark_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            task = self._get_or_create_task(task_id)
            task.state = TaskState.FAILED
            task.last_error = error
            self._touch(task)

    def stop_task(self, task_id: str, timeout: float = 10.0, disable: bool = False) -> bool:
        with self._lock:
            task = self._get_or_create_task(task_id)
            handle = self._handles.setdefault(task_id, TaskHandle())
            handle.request_stop()
            task.state = TaskState.STOPPING
            self._touch(task)
            process = handle.process

        if process and process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write(b"q")
                    process.stdin.close()
                else:
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=timeout)
            except (OSError, TimeoutExpired):
                process.terminate()

        with self._lock:
            if disable:
                task.enabled = False
                task.state = TaskState.OFFLINE
            else:
                task.state = TaskState.MONITORING
            self._touch(task)
            self._handles.setdefault(task_id, TaskHandle()).process = None
            return True

    def reload_from_url_config(self, url_tuples: list[tuple[str, str, str]], comments: list[str]) -> None:
        """Sync current task metadata from URL config parsing results."""
        with self._lock:
            active_ids: set[str] = set()
            disabled_ids: set[str] = set()
            for quality, url, anchor_name in url_tuples:
                task_id = url
                active_ids.add(task_id)
                task = self._get_or_create_task(task_id, url)
                task.quality = quality
                task.anchor_name = anchor_name or task.anchor_name
                task.enabled = True
                if task.state in (TaskState.OFFLINE, TaskState.FAILED):
                    task.state = TaskState.MONITORING
                self._touch(task)

            for disabled_url in comments:
                task = self._get_or_create_task(disabled_url, disabled_url)
                task.enabled = False
                task.state = TaskState.OFFLINE
                disabled_ids.add(disabled_url)
                self._touch(task)

            known_enabled = {k for k, v in self._tasks.items() if v.enabled}
            stale = known_enabled - active_ids
            for task_id in stale:
                task = self._tasks[task_id]
                task.enabled = False
                task.state = TaskState.OFFLINE
                self._touch(task)

            # Remove tasks that no longer exist in URL config to avoid ghost entries after delete.
            present_ids = active_ids | disabled_ids
            removed_ids = [task_id for task_id in self._tasks.keys() if task_id not in present_ids]
            for task_id in removed_ids:
                self._tasks.pop(task_id, None)
                self._handles.pop(task_id, None)

    def get_snapshot(self) -> dict[str, dict[str, str | bool | float | None]]:
        with self._lock:
            snapshot: dict[str, dict[str, str | bool | float | None]] = {}
            for task_id, task in self._tasks.items():
                snapshot[task_id] = {
                    "task_id": task.task_id,
                    "url": task.url,
                    "quality": task.quality,
                    "anchor_name": task.anchor_name,
                    "enabled": task.enabled,
                    "state": task.state.value,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "started_recording_at": task.started_recording_at,
                    "last_error": task.last_error,
                }
            return snapshot

    def get_task(self, task_id: str) -> RuntimeTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def remove_task(self, task_id: str) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)
            self._handles.pop(task_id, None)
