from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ProbeResult:
    platform: str
    port_info: dict[str, Any]
    new_record_url: str = ""


class RecordingFlowService:
    """Injectable 3-layer flow: probe -> select source -> execute recording."""

    def __init__(
        self,
        probe_handler: Callable[[str, str, str | None, bool], ProbeResult],
        source_selector: Callable[[str, dict[str, Any]], str | None],
        execute_handler: Callable[..., tuple[bool, bool]] | None = None,
    ) -> None:
        self._probe_handler = probe_handler
        self._source_selector = source_selector
        self._execute_handler = execute_handler

    def probe(self, record_url: str, record_quality: str, proxy_address: str | None, global_proxy: bool) -> ProbeResult:
        return self._probe_handler(record_url, record_quality, proxy_address, global_proxy)

    def select_source(self, record_url: str, stream_info: dict[str, Any]) -> str | None:
        return self._source_selector(record_url, stream_info)

    def execute(self, **kwargs: Any) -> tuple[bool, bool]:
        if self._execute_handler is None:
            return False, False
        return self._execute_handler(**kwargs)
