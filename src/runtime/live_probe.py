from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from src import spider, stream, utils

from .config_service import RuntimeConfigService


logger = logging.getLogger(__name__)

QUALITY_CODE_MAPPING = {
    "原画": "OD",
    "蓝光": "BD",
    "超清": "UHD",
    "高清": "HD",
    "标清": "SD",
    "流畅": "LD",
}


@dataclass
class LiveProbeResult:
    supported: bool
    is_live: bool | None
    anchor_name: str = ""
    error: str = ""
    record_url: str = ""
    platform: str = ""
    title: str = ""


class LiveStatusProbe:
    """Lightweight live-state probe service used by the Web runtime."""

    def __init__(self, config_file_path: str | Path | RuntimeConfigService, *, max_workers: int = 3) -> None:
        if isinstance(config_file_path, RuntimeConfigService):
            self._config_service = config_file_path
        else:
            self._config_service = RuntimeConfigService(config_file_path)

        self._lock = threading.RLock()
        self._max_workers = max(1, int(max_workers))
        self._semaphore = threading.Semaphore(self._max_workers)

        self._use_proxy = False
        self._proxy_addr: str | None = None
        self._cookies: dict[str, str] = {}

        self._reload_config(force=True)

    def probe(self, url: str, quality_zh: str) -> LiveProbeResult:
        self._reload_config()
        url_value = (url or "").strip()
        if not url_value:
            return LiveProbeResult(supported=False, is_live=None, error="empty url")

        quality_code = QUALITY_CODE_MAPPING.get((quality_zh or "").strip(), "OD")
        proxy_address = self._proxy_addr if self._use_proxy and self._proxy_addr else None

        try:
            if "douyin.com/" in url_value:
                with self._semaphore:
                    if "v.douyin.com" not in url_value and "/user/" not in url_value:
                        json_data = self._run_async(
                            spider.get_douyin_stream_data(
                                url=url_value,
                                proxy_addr=proxy_address,
                                cookies=self._cookies.get("douyin", ""),
                            )
                        )
                    else:
                        json_data = self._run_async(
                            spider.get_douyin_app_stream_data(
                                url=url_value,
                                proxy_addr=proxy_address,
                                cookies=self._cookies.get("douyin", ""),
                            )
                        )
                    port_info = self._run_async(
                        stream.get_douyin_stream_url(json_data, quality_code, proxy_address)
                    )
                return self._to_result(port_info, platform="douyin")

            if "tiktok.com/" in url_value:
                if not proxy_address:
                    return LiveProbeResult(
                        supported=True,
                        is_live=None,
                        error="",
                    )
                with self._semaphore:
                    json_data = self._run_async(
                        spider.get_tiktok_stream_data(
                            url=url_value,
                            proxy_addr=proxy_address,
                            cookies=self._cookies.get("tiktok", ""),
                        )
                    )
                    port_info = self._run_async(
                        stream.get_tiktok_stream_url(json_data, quality_code, proxy_address)
                    )
                return self._to_result(port_info, platform="tiktok")

            if "live.kuaishou.com/" in url_value:
                with self._semaphore:
                    json_data = self._run_async(
                        spider.get_kuaishou_stream_data(
                            url=url_value,
                            proxy_addr=proxy_address,
                            cookies=self._cookies.get("kuaishou", ""),
                        )
                    )
                    port_info = self._run_async(stream.get_kuaishou_stream_url(json_data, quality_code))
                return self._to_result(port_info, platform="kuaishou")

            if "www.huya.com/" in url_value:
                with self._semaphore:
                    if quality_code in {"OD", "BD", "UHD"}:
                        port_info = self._run_async(
                            spider.get_huya_app_stream_url(
                                url=url_value,
                                proxy_addr=proxy_address,
                                cookies=self._cookies.get("huya", ""),
                            )
                        )
                    else:
                        json_data = self._run_async(
                            spider.get_huya_stream_data(
                                url=url_value,
                                proxy_addr=proxy_address,
                                cookies=self._cookies.get("huya", ""),
                            )
                        )
                        port_info = self._run_async(stream.get_huya_stream_url(json_data, quality_code))
                    return self._to_result(port_info, platform="huya")

            if "www.douyu.com/" in url_value:
                with self._semaphore:
                    json_data = self._run_async(
                        spider.get_douyu_info_data(
                            url=url_value,
                            proxy_addr=proxy_address,
                            cookies=self._cookies.get("douyu", ""),
                        )
                    )
                    port_info = self._run_async(
                        stream.get_douyu_stream_url(
                            json_data,
                            video_quality=quality_code,
                            cookies=self._cookies.get("douyu", ""),
                            proxy_addr=proxy_address,
                        )
                    )
                return self._to_result(port_info, platform="douyu")

            if "live.bilibili.com/" in url_value:
                with self._semaphore:
                    json_data = self._run_async(
                        spider.get_bilibili_room_info(
                            url=url_value,
                            proxy_addr=proxy_address,
                            cookies=self._cookies.get("bilibili", ""),
                        )
                    )
                    port_info = self._run_async(
                        stream.get_bilibili_stream_url(
                            json_data,
                            video_quality=quality_code,
                            cookies=self._cookies.get("bilibili", ""),
                            proxy_addr=proxy_address,
                        )
                    )
                return self._to_result(port_info, platform="bilibili")

            if "xhslink.com/" in url_value or "xiaohongshu.com/" in url_value:
                with self._semaphore:
                    port_info = self._run_async(
                        spider.get_xhs_stream_url(
                            url_value,
                            proxy_addr=proxy_address,
                            cookies=self._cookies.get("xiaohongshu", ""),
                        )
                    )
                return self._to_result(port_info, platform="xiaohongshu")

            if ".m3u8" in url_value or ".flv" in url_value:
                return LiveProbeResult(
                    supported=True,
                    is_live=True,
                    anchor_name="自定义录制直播",
                    record_url=url_value,
                    platform="custom",
                )

            return LiveProbeResult(supported=False, is_live=None)
        except Exception as exc:  # pragma: no cover - runtime network path
            logger.warning("probe failed for %s: %s", url_value, exc)
            return LiveProbeResult(supported=True, is_live=None, error=str(exc))

    @staticmethod
    def _run_async(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result_holder: dict[str, object] = {}
        error_holder: dict[str, Exception] = {}

        def _runner() -> None:
            try:
                result_holder["value"] = asyncio.run(coro)
            except Exception as exc:  # pragma: no cover - runtime async path
                error_holder["error"] = exc

        worker = threading.Thread(target=_runner, daemon=True)
        worker.start()
        worker.join()

        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("value")

    def _reload_config(self, *, force: bool = False) -> None:
        with self._lock:
            self._config_service.reload_if_needed(force=force)
            values = self._config_service.get_values()

            max_workers = max(1, int(values.max_request_workers))
            if max_workers != self._max_workers:
                self._semaphore = threading.Semaphore(max_workers)
                self._max_workers = max_workers

            self._use_proxy = values.use_proxy
            self._proxy_addr = utils.handle_proxy_addr(values.proxy_addr)
            self._cookies = dict(values.cookies)

    @staticmethod
    def _to_result(port_info: object, *, platform: str) -> LiveProbeResult:
        if not isinstance(port_info, dict):
            return LiveProbeResult(supported=True, is_live=None, error="invalid probe response")

        anchor_name = str(port_info.get("anchor_name") or "")
        is_live_raw = port_info.get("is_live")
        if isinstance(is_live_raw, bool):
            is_live = is_live_raw
        elif is_live_raw in (0, 1):
            is_live = bool(is_live_raw)
        elif isinstance(is_live_raw, str):
            lowered = is_live_raw.strip().lower()
            if lowered in {"1", "true", "on", "live", "yes", "y", "是"}:
                is_live = True
            elif lowered in {"0", "false", "off", "not_live", "no", "n", "否"}:
                is_live = False
            else:
                is_live = None
        else:
            is_live = None

        record_url = str(
            port_info.get("record_url")
            or port_info.get("flv_url")
            or port_info.get("m3u8_url")
            or ""
        )
        title = str(port_info.get("title") or "")

        # 部分平台偶发不返回明确直播标记，但会返回有效流地址。
        if is_live is not True and record_url:
            is_live = True

        return LiveProbeResult(
            supported=True,
            is_live=is_live,
            anchor_name=anchor_name,
            record_url=record_url,
            platform=platform,
            title=title,
        )
