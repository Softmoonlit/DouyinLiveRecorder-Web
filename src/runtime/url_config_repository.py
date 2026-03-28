from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_QUALITIES = ("原画", "蓝光", "超清", "高清", "标清", "流畅")


@dataclass
class UrlConfigTask:
    quality: str
    url: str
    anchor_name: str = ""
    enabled: bool = True

    @property
    def task_id(self) -> str:
        return self.url


class UrlConfigRepository:
    """Thread-safe read/write adapter for config/URL_config.ini."""

    def __init__(self, file_path: str | Path, encoding: str = "utf-8-sig") -> None:
        self._file_path = Path(file_path)
        self._encoding = encoding
        self._lock = threading.RLock()

    def ensure_file(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._file_path.exists():
            self._file_path.write_text("", encoding=self._encoding)

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load_tasks(self, default_quality: str = "原画") -> list[UrlConfigTask]:
        with self._lock:
            self.ensure_file()
            lines = self._file_path.read_text(encoding=self._encoding, errors="ignore").splitlines()
            tasks: list[UrlConfigTask] = []
            seen: set[str] = set()

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue

                enabled = not line.startswith("#")
                if not enabled:
                    line = line[1:].strip()
                task = self._parse_line(line, enabled=enabled, default_quality=default_quality)
                if task is None:
                    continue
                if task.url in seen:
                    continue
                seen.add(task.url)
                tasks.append(task)
            return tasks

    def save_tasks(self, tasks: list[UrlConfigTask]) -> None:
        with self._lock:
            self.ensure_file()
            lines = [self._serialize_task(task) for task in tasks]
            payload = "\n".join(lines)
            if payload:
                payload += "\n"
            self._file_path.write_text(payload, encoding=self._encoding)

    def upsert_task(self, task: UrlConfigTask, default_quality: str = "原画") -> UrlConfigTask:
        with self._lock:
            tasks = self.load_tasks(default_quality=default_quality)
            for idx, item in enumerate(tasks):
                if item.url == task.url:
                    tasks[idx] = task
                    self.save_tasks(tasks)
                    return task
            tasks.append(task)
            self.save_tasks(tasks)
            return task

    def delete_task(self, task_id: str, default_quality: str = "原画") -> bool:
        with self._lock:
            tasks = self.load_tasks(default_quality=default_quality)
            filtered = [task for task in tasks if task.task_id != task_id]
            changed = len(filtered) != len(tasks)
            if changed:
                self.save_tasks(filtered)
            return changed

    def set_task_enabled(self, task_id: str, enabled: bool, default_quality: str = "原画") -> bool:
        with self._lock:
            tasks = self.load_tasks(default_quality=default_quality)
            found = False
            for task in tasks:
                if task.task_id == task_id:
                    task.enabled = enabled
                    found = True
                    break
            if found:
                self.save_tasks(tasks)
            return found

    def update_task(
        self,
        task_id: str,
        *,
        quality: str | None = None,
        anchor_name: str | None = None,
        new_url: str | None = None,
        enabled: bool | None = None,
        default_quality: str = "原画",
    ) -> UrlConfigTask | None:
        with self._lock:
            tasks = self.load_tasks(default_quality=default_quality)
            for idx, task in enumerate(tasks):
                if task.task_id != task_id:
                    continue
                task.quality = self._normalize_quality(quality or task.quality, default_quality)
                if anchor_name is not None:
                    task.anchor_name = anchor_name.strip()
                if new_url is not None:
                    task.url = self._normalize_url(new_url)
                if enabled is not None:
                    task.enabled = enabled
                tasks[idx] = task
                self.save_tasks(tasks)
                return task
            return None

    @staticmethod
    def _normalize_url(url: str) -> str:
        value = url.strip()
        if not value:
            return value
        if "://" not in value:
            return f"https://{value}"
        return value

    @staticmethod
    def _normalize_quality(value: str, default_quality: str) -> str:
        q = value.strip() if value else ""
        return q if q in SUPPORTED_QUALITIES else default_quality

    def _parse_line(self, line: str, *, enabled: bool, default_quality: str) -> UrlConfigTask | None:
        split_line = [item.strip() for item in line.replace("，", ",").split(",")]
        split_line = [item for item in split_line if item != ""]
        if not split_line:
            return None

        if len(split_line) == 1:
            quality, url, name = default_quality, split_line[0], ""
        elif len(split_line) == 2:
            first, second = split_line
            if "://" in first or "." in first:
                quality, url, name = default_quality, first, second
            else:
                quality, url, name = first, second, ""
        else:
            quality, url, name = split_line[0], split_line[1], split_line[2]

        quality = self._normalize_quality(quality, default_quality)
        url = self._normalize_url(url)
        if not url:
            return None
        return UrlConfigTask(quality=quality, url=url, anchor_name=name, enabled=enabled)

    @staticmethod
    def _serialize_task(task: UrlConfigTask) -> str:
        body = f"{task.quality},{task.url}"
        if task.anchor_name:
            body += f",{task.anchor_name}"
        return body if task.enabled else f"#{body}"
