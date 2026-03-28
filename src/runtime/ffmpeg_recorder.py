from __future__ import annotations

import configparser
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .live_probe import LiveProbeResult


SUPPORTED_FORMATS = {"TS", "FLV", "MP4", "MKV"}


@dataclass
class RecordingStartResult:
    started: bool
    message: str = ""
    process: subprocess.Popen | None = None
    output_file: str = ""


class FfmpegRecordingService:
    """Start ffmpeg recording process for a single task."""

    def __init__(self, config_file_path: str | Path, *, default_download_root: str | Path) -> None:
        self._config_file_path = Path(config_file_path)
        self._default_download_root = Path(default_download_root)
        self._lock = threading.RLock()
        self._config_mtime: float = -1.0

        self._save_root = self._default_download_root
        self._save_format = "TS"
        self._folder_by_author = True
        self._folder_by_time = False
        self._force_https = False

        self._reload_config(force=True)

    def start_recording(self, task: dict, probe_result: LiveProbeResult) -> RecordingStartResult:
        if probe_result.is_live is not True:
            return RecordingStartResult(started=False, message="room is not live")

        record_url = str(probe_result.record_url or "").strip()
        if not record_url:
            return RecordingStartResult(started=False, message="empty record url")

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return RecordingStartResult(started=False, message="ffmpeg not found")

        self._reload_config()
        if self._force_https and record_url.startswith("http://"):
            record_url = record_url.replace("http://", "https://", 1)

        output_path = self._build_output_path(task=task, probe_result=probe_result)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg_cmd = [
            ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-hide_banner",
            "-rw_timeout",
            "15000000",
            "-i",
            record_url,
            "-map",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
        ]

        suffix = output_path.suffix.lower()
        if suffix == ".ts":
            ffmpeg_cmd.extend(["-f", "mpegts", str(output_path)])
        elif suffix == ".flv":
            ffmpeg_cmd.extend(["-f", "flv", str(output_path)])
        elif suffix == ".mp4":
            ffmpeg_cmd.extend(["-movflags", "+frag_keyframe+empty_moov", "-f", "mp4", str(output_path)])
        elif suffix == ".mkv":
            ffmpeg_cmd.extend(["-f", "matroska", str(output_path)])
        else:
            ffmpeg_cmd.extend(["-f", "mpegts", str(output_path.with_suffix(".ts"))])
            output_path = output_path.with_suffix(".ts")

        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # pragma: no cover - system path
            return RecordingStartResult(started=False, message=f"failed to start ffmpeg: {exc}")

        return RecordingStartResult(
            started=True,
            process=process,
            output_file=str(output_path),
            message="recording started",
        )

    def _reload_config(self, *, force: bool = False) -> None:
        with self._lock:
            if not self._config_file_path.exists():
                return

            current_mtime = self._config_file_path.stat().st_mtime
            if not force and current_mtime == self._config_mtime:
                return

            parser = configparser.RawConfigParser()
            parser.read(self._config_file_path, encoding="utf-8-sig")

            save_root = self._get_value(parser, "录制设置", "直播保存路径(不填则默认)", "").strip()
            self._save_root = Path(save_root) if save_root else self._default_download_root

            save_format = self._get_value(
                parser,
                "录制设置",
                "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频",
                "ts",
            ).strip().upper()
            self._save_format = save_format if save_format in SUPPORTED_FORMATS else "TS"

            self._folder_by_author = self._get_bool_value(parser, "录制设置", "保存文件夹是否以作者区分", True)
            self._folder_by_time = self._get_bool_value(parser, "录制设置", "保存文件夹是否以时间区分", False)
            self._force_https = self._get_bool_value(parser, "录制设置", "是否强制启用https录制", False)
            self._config_mtime = current_mtime

    def _build_output_path(self, *, task: dict, probe_result: LiveProbeResult) -> Path:
        now = datetime.now()
        anchor_name = self._sanitize_name(str(task.get("anchor_name") or probe_result.anchor_name or "主播"))
        platform = self._sanitize_name(str(probe_result.platform or task.get("platform") or "other"))

        output_dir = self._save_root / platform
        if self._folder_by_author:
            output_dir = output_dir / anchor_name
        if self._folder_by_time:
            output_dir = output_dir / now.strftime("%Y-%m-%d")

        filename = f"{anchor_name}_{now.strftime('%Y-%m-%d_%H-%M-%S')}.{self._save_format.lower()}"
        return output_dir / filename

    @staticmethod
    def _sanitize_name(value: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", value.strip()).strip("_")
        return cleaned or "unknown"

    @staticmethod
    def _get_value(parser: configparser.RawConfigParser, section: str, option: str, default: str) -> str:
        try:
            return parser.get(section, option)
        except (configparser.NoOptionError, configparser.NoSectionError):
            return default

    @staticmethod
    def _get_bool_value(
        parser: configparser.RawConfigParser,
        section: str,
        option: str,
        default: bool,
    ) -> bool:
        mapping = {"是": True, "否": False, "true": True, "false": False, "1": True, "0": False}
        raw_value = FfmpegRecordingService._get_value(parser, section, option, "是" if default else "否")
        return mapping.get(str(raw_value).strip().lower(), default)
