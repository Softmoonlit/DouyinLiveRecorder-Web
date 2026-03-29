from __future__ import annotations

import configparser
import copy
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


SUPPORTED_QUALITIES = ("原画", "蓝光", "超清", "高清", "标清", "流畅")
SUPPORTED_SAVE_FORMATS = ("TS", "FLV", "MP4", "MKV")


@dataclass
class RuntimeConfigValues:
	default_quality: str = "原画"
	video_save_path: str = ""
	save_format: str = "TS"
	folder_by_author: bool = True
	folder_by_time: bool = False
	split_recording: bool = False
	split_time_seconds: int = 1800
	convert_to_mp4: bool = False
	convert_to_h264: bool = False
	delete_origin_after_convert: bool = False
	force_https_recording: bool = False
	probe_interval_seconds: float = 8.0
	use_proxy: bool = False
	proxy_addr: str = ""
	cookies: dict[str, str] = field(default_factory=dict)


@dataclass
class ConfigReloadResult:
	success: bool
	changed: bool
	reloaded_at: float
	config_mtime: float
	warnings: list[str] = field(default_factory=list)
	error: str = ""


class RuntimeConfigService:
	"""Thread-safe typed loader for config/config.ini values used by Web runtime."""

	def __init__(self, config_file_path: str | Path, *, encoding: str = "utf-8-sig") -> None:
		self._config_file_path = Path(config_file_path)
		self._encoding = encoding
		self._lock = threading.RLock()

		self._config_mtime: float = -1.0
		self._values = RuntimeConfigValues()
		self._last_result = ConfigReloadResult(
			success=True,
			changed=False,
			reloaded_at=time.time(),
			config_mtime=-1.0,
			warnings=[],
			error="",
		)

		self.reload_if_needed(force=True)

	def reload_if_needed(self, *, force: bool = False) -> ConfigReloadResult:
		with self._lock:
			now = time.time()
			if not self._config_file_path.exists():
				self._last_result = ConfigReloadResult(
					success=False,
					changed=False,
					reloaded_at=now,
					config_mtime=-1.0,
					warnings=["config file not found, using runtime defaults"],
					error="config file not found",
				)
				return copy.deepcopy(self._last_result)

			current_mtime = self._config_file_path.stat().st_mtime
			if not force and current_mtime == self._config_mtime:
				unchanged_result = copy.deepcopy(self._last_result)
				unchanged_result.changed = False
				unchanged_result.reloaded_at = now
				unchanged_result.config_mtime = current_mtime
				return unchanged_result

			parser = configparser.RawConfigParser()
			warnings: list[str] = []

			try:
				parser.read(self._config_file_path, encoding=self._encoding)

				values = RuntimeConfigValues(
					default_quality=self._read_quality(
						parser,
						section="录制设置",
						option="原画|超清|高清|标清|流畅",
						default="原画",
						warnings=warnings,
					),
					video_save_path=self._read_value(
						parser,
						section="录制设置",
						option="直播保存路径(不填则默认)",
						default="",
					).strip(),
					save_format=self._read_save_format(
						parser,
						section="录制设置",
						option="视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频",
						default="TS",
						warnings=warnings,
					),
					folder_by_author=self._read_bool(
						parser,
						section="录制设置",
						option="保存文件夹是否以作者区分",
						default=True,
						warnings=warnings,
					),
					folder_by_time=self._read_bool(
						parser,
						section="录制设置",
						option="保存文件夹是否以时间区分",
						default=False,
						warnings=warnings,
					),
					split_recording=self._read_bool(
						parser,
						section="录制设置",
						option="分段录制是否开启",
						default=False,
						warnings=warnings,
					),
					split_time_seconds=self._read_int(
						parser,
						section="录制设置",
						option="视频分段时间(秒)",
						default=1800,
						minimum=60,
						maximum=43200,
						warnings=warnings,
					),
					convert_to_mp4=self._read_bool(
						parser,
						section="录制设置",
						option="录制完成后自动转为mp4格式",
						default=False,
						warnings=warnings,
					),
					convert_to_h264=self._read_bool(
						parser,
						section="录制设置",
						option="mp4格式重新编码为h264",
						default=False,
						warnings=warnings,
					),
					delete_origin_after_convert=self._read_bool(
						parser,
						section="录制设置",
						option="追加格式后删除原文件",
						default=False,
						warnings=warnings,
					),
					force_https_recording=self._read_bool(
						parser,
						section="录制设置",
						option="是否强制启用https录制",
						default=False,
						warnings=warnings,
					),
					probe_interval_seconds=float(
						self._read_int(
							parser,
							section="录制设置",
							option="循环时间(秒)",
							default=8,
							minimum=2,
							maximum=300,
							warnings=warnings,
						)
					),
					use_proxy=self._read_bool(
						parser,
						section="录制设置",
						option="是否使用代理ip(是/否)",
						default=False,
						warnings=warnings,
					),
					proxy_addr=self._read_value(
						parser,
						section="录制设置",
						option="代理地址",
						default="",
					).strip(),
					cookies={
						"douyin": self._read_value(parser, "Cookie", "抖音cookie", ""),
						"tiktok": self._read_value(parser, "Cookie", "tiktok_cookie", ""),
						"kuaishou": self._read_value(parser, "Cookie", "快手cookie", ""),
						"huya": self._read_value(parser, "Cookie", "虎牙cookie", ""),
						"douyu": self._read_value(parser, "Cookie", "斗鱼cookie", ""),
						"bilibili": self._read_value(parser, "Cookie", "B站cookie", ""),
						"xiaohongshu": self._read_value(parser, "Cookie", "小红书cookie", ""),
					},
				)

				self._values = values
				self._config_mtime = current_mtime
				self._last_result = ConfigReloadResult(
					success=True,
					changed=True,
					reloaded_at=now,
					config_mtime=current_mtime,
					warnings=warnings,
					error="",
				)
			except Exception as exc:  # pragma: no cover - runtime path
				self._last_result = ConfigReloadResult(
					success=False,
					changed=False,
					reloaded_at=now,
					config_mtime=current_mtime,
					warnings=warnings,
					error=f"config reload failed: {exc}",
				)

			return copy.deepcopy(self._last_result)

	def get_values(self) -> RuntimeConfigValues:
		with self._lock:
			return copy.deepcopy(self._values)

	def get_snapshot(self, *, mask_sensitive: bool = True) -> dict:
		with self._lock:
			values = asdict(self._values)
			if mask_sensitive:
				values["cookies"] = {
					key: self._mask_value(value)
					for key, value in values.get("cookies", {}).items()
				}
				values["proxy_addr"] = self._mask_value(values.get("proxy_addr", ""))

			return {
				"config_path": str(self._config_file_path),
				"last_reload": {
					"success": self._last_result.success,
					"changed": self._last_result.changed,
					"reloaded_at": self._last_result.reloaded_at,
					"config_mtime": self._last_result.config_mtime,
					"warnings": list(self._last_result.warnings),
					"error": self._last_result.error,
				},
				"values": values,
			}

	@staticmethod
	def _read_value(
		parser: configparser.RawConfigParser,
		section: str,
		option: str,
		default: str,
	) -> str:
		try:
			return parser.get(section, option)
		except (configparser.NoOptionError, configparser.NoSectionError):
			return default

	@staticmethod
	def _read_bool(
		parser: configparser.RawConfigParser,
		*,
		section: str,
		option: str,
		default: bool,
		warnings: list[str],
	) -> bool:
		raw = RuntimeConfigService._read_value(
			parser,
			section=section,
			option=option,
			default="是" if default else "否",
		)
		mapping = {
			"是": True,
			"否": False,
			"true": True,
			"false": False,
			"1": True,
			"0": False,
		}
		key = str(raw).strip().lower()
		if key in mapping:
			return mapping[key]
		warnings.append(f"invalid bool value at {section}.{option}: {raw!r}, fallback to {default}")
		return default

	@staticmethod
	def _read_int(
		parser: configparser.RawConfigParser,
		*,
		section: str,
		option: str,
		default: int,
		minimum: int,
		maximum: int,
		warnings: list[str],
	) -> int:
		raw = RuntimeConfigService._read_value(parser, section=section, option=option, default=str(default))
		try:
			value = int(str(raw).strip())
		except (TypeError, ValueError):
			warnings.append(f"invalid int value at {section}.{option}: {raw!r}, fallback to {default}")
			return default

		clamped = max(minimum, min(maximum, value))
		if clamped != value:
			warnings.append(
				f"out-of-range int at {section}.{option}: {value}, clamped to [{minimum}, {maximum}] => {clamped}"
			)
		return clamped

	@staticmethod
	def _read_quality(
		parser: configparser.RawConfigParser,
		*,
		section: str,
		option: str,
		default: str,
		warnings: list[str],
	) -> str:
		raw = RuntimeConfigService._read_value(parser, section=section, option=option, default=default).strip()
		if raw in SUPPORTED_QUALITIES:
			return raw
		warnings.append(f"invalid quality at {section}.{option}: {raw!r}, fallback to {default}")
		return default

	@staticmethod
	def _read_save_format(
		parser: configparser.RawConfigParser,
		*,
		section: str,
		option: str,
		default: str,
		warnings: list[str],
	) -> str:
		raw = RuntimeConfigService._read_value(parser, section=section, option=option, default=default).strip().upper()
		if raw in SUPPORTED_SAVE_FORMATS:
			return raw
		warnings.append(f"invalid save format at {section}.{option}: {raw!r}, fallback to {default}")
		return default

	@staticmethod
	def _mask_value(raw: str) -> str:
		value = str(raw or "")
		if not value:
			return ""
		if len(value) <= 8:
			return "*" * len(value)
		return f"{value[:3]}***{value[-2:]}"

