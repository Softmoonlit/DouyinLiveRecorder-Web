from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from subprocess import Popen
from typing import Any


class TaskState(str, Enum):
    OFFLINE = "offline"
    MONITORING = "monitoring"
    LIVE_NOT_RECORDING = "live_not_recording"
    RECORDING = "recording"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass
class RuntimeTask:
    task_id: str
    url: str
    quality: str = "原画"
    anchor_name: str = ""
    enabled: bool = True
    state: TaskState = TaskState.MONITORING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_recording_at: float | None = None
    last_error: str = ""


@dataclass
class TaskHandle:
    monitor_thread: threading.Thread | None = None
    process: Popen[Any] | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)

    def request_stop(self) -> None:
        self.stop_event.set()

    def reset_stop_flag(self) -> None:
        self.stop_event.clear()

    def should_stop(self) -> bool:
        return self.stop_event.is_set()
