from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .config_service import RuntimeConfigService
from .live_probe import LiveProbeResult


SUPPORTED_FORMATS = {"TS", "FLV", "MP4", "MKV"}
logger = logging.getLogger(__name__)


@dataclass
class RecordingStartResult:
    started: bool
    message: str = ""
    process: subprocess.Popen | None = None
    output_file: str = ""


class FfmpegRecordingService:
    """Start ffmpeg recording process for a single task."""

    def __init__(
        self,
        config_file_path: str | Path | RuntimeConfigService,
        *,
        default_download_root: str | Path,
    ) -> None:
        if isinstance(config_file_path, RuntimeConfigService):
            self._config_service = config_file_path
        else:
            self._config_service = RuntimeConfigService(config_file_path)

        self._default_download_root = Path(default_download_root)
        self._lock = threading.RLock()

        self._save_root = self._default_download_root
        self._save_format = "TS"
        self._folder_by_author = True
        self._folder_by_time = False
        self._force_https = False
        self._split_recording = False
        self._split_time_seconds = 1800
        self._convert_to_mp4 = False
        self._convert_to_h264 = False
        self._delete_origin_after_convert = False

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

        output_target: Path = output_path
        suffix = output_path.suffix.lower()
        if self._split_recording:
            segment_output = self._build_segment_template(output_path)
            ffmpeg_cmd.extend([
                "-f",
                "segment",
                "-segment_time",
                str(self._split_time_seconds),
                "-reset_timestamps",
                "1",
            ])
            segment_format = self._segment_format_for_suffix(suffix)
            if segment_format:
                ffmpeg_cmd.extend(["-segment_format", segment_format])
            ffmpeg_cmd.append(str(segment_output))
            output_target = segment_output
        else:
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
            output_target = output_path

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
            output_file=str(output_target),
            message="recording started",
        )

    def finalize_recording(self, output_file: str) -> tuple[bool, str]:
        """Post-process output after ffmpeg exits, based on runtime config policy."""
        self._reload_config()

        source = Path(str(output_file or "").strip())
        if not source.name:
            return True, output_file

        # Segmented template path, no single-file conversion possible.
        if "%" in source.name:
            return True, output_file

        if not source.exists():
            return True, output_file

        if not self._convert_to_mp4:
            return True, str(source)

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return False, "ffmpeg not found for post-processing"

        target = source.with_suffix(".mp4")
        if target == source:
            target = source.with_name(f"{source.stem}_converted.mp4")

        ffmpeg_cmd = [
            ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-hide_banner",
            "-i",
            str(source),
        ]

        if self._convert_to_h264:
            ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"])
        else:
            ffmpeg_cmd.extend(["-c", "copy"])
        ffmpeg_cmd.append(str(target))

        try:
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:  # pragma: no cover - ffmpeg runtime path
            return False, f"post-process conversion failed: {exc}"

        if self._delete_origin_after_convert:
            try:
                source.unlink(missing_ok=True)
            except Exception as exc:  # pragma: no cover - filesystem path
                logger.warning("failed to delete original recording file %s: %s", source, exc)

        return True, str(target)

    def _reload_config(self, *, force: bool = False) -> None:
        with self._lock:
            result = self._config_service.reload_if_needed(force=force)
            if not result.success and result.error:
                logger.warning(result.error)

            values = self._config_service.get_values()
            save_root = values.video_save_path.strip()
            self._save_root = Path(save_root) if save_root else self._default_download_root

            save_format = values.save_format.strip().upper()
            self._save_format = save_format if save_format in SUPPORTED_FORMATS else "TS"

            self._folder_by_author = values.folder_by_author
            self._folder_by_time = values.folder_by_time
            self._force_https = values.force_https_recording
            self._split_recording = values.split_recording
            self._split_time_seconds = values.split_time_seconds
            self._convert_to_mp4 = values.convert_to_mp4
            self._convert_to_h264 = values.convert_to_h264
            self._delete_origin_after_convert = values.delete_origin_after_convert

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
    def _segment_format_for_suffix(suffix: str) -> str:
        if suffix == ".ts":
            return "mpegts"
        if suffix == ".flv":
            return "flv"
        if suffix == ".mp4":
            return "mp4"
        if suffix == ".mkv":
            return "matroska"
        return "mpegts"

    @staticmethod
    def _build_segment_template(output_path: Path) -> Path:
        return output_path.with_name(f"{output_path.stem}_%03d{output_path.suffix}")
