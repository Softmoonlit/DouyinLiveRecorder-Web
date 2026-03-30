from __future__ import annotations

import configparser
import copy
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_QUALITIES = ("原画", "蓝光", "超清", "高清", "标清", "流畅")
SUPPORTED_SAVE_FORMATS = ("TS", "FLV", "MP4", "MKV")


SETTINGS_FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "video_save_path": {
        "label": "视频保存路径",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "直播保存路径(不填则默认)",
        "type": "string",
        "default": "",
        "effect": "新增任务立即生效",
    },
    "default_quality": {
        "label": "默认画质",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "原画|超清|高清|标清|流畅",
        "type": "enum",
        "choices": list(SUPPORTED_QUALITIES),
        "default": "原画",
        "effect": "新增任务立即生效",
    },
    "split_recording": {
        "label": "分段录制",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "分段录制是否开启",
        "type": "bool",
        "default": False,
        "effect": "新增任务立即生效",
    },
    "split_time_seconds": {
        "label": "分段时长(秒)",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "视频分段时间(秒)",
        "type": "int",
        "minimum": 60,
        "maximum": 43200,
        "default": 1800,
        "effect": "新增任务立即生效",
    },
    "save_format": {
        "label": "保存格式",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频",
        "type": "enum",
        "choices": list(SUPPORTED_SAVE_FORMATS),
        "default": "TS",
        "normalize_upper": True,
        "effect": "新增任务立即生效",
    },
    "convert_to_mp4": {
        "label": "自动转 MP4",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "录制完成后自动转为mp4格式",
        "type": "bool",
        "default": False,
        "effect": "新增任务立即生效",
    },
    "convert_to_h264": {
        "label": "MP4 转 H264",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "mp4格式重新编码为h264",
        "type": "bool",
        "default": False,
        "effect": "新增任务立即生效",
    },
    "delete_origin_after_convert": {
        "label": "转码后删除原文件",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "追加格式后删除原文件",
        "type": "bool",
        "default": False,
        "effect": "新增任务立即生效",
    },
    "probe_interval_seconds": {
        "label": "循环间隔(秒)",
        "group": "第一批（录制核心）",
        "batch": 1,
        "section": "录制设置",
        "option": "循环时间(秒)",
        "type": "int",
        "minimum": 2,
        "maximum": 300,
        "default": 8,
        "effect": "下轮循环生效",
    },
    "use_proxy": {
        "label": "启用代理",
        "group": "第二批（网络与稳定性）",
        "batch": 2,
        "section": "录制设置",
        "option": "是否使用代理ip(是/否)",
        "type": "bool",
        "default": True,
        "effect": "下轮探测生效",
    },
    "proxy_addr": {
        "label": "代理地址",
        "group": "第二批（网络与稳定性）",
        "batch": 2,
        "section": "录制设置",
        "option": "代理地址",
        "type": "string",
        "default": "",
        "effect": "下轮探测生效",
    },
    "max_request_workers": {
        "label": "并发线程数",
        "group": "第二批（网络与稳定性）",
        "batch": 2,
        "section": "录制设置",
        "option": "同一时间访问网络的线程数",
        "type": "int",
        "minimum": 1,
        "maximum": 64,
        "default": 3,
        "effect": "下轮探测生效",
    },
    "force_https_recording": {
        "label": "强制 HTTPS 录制",
        "group": "第二批（网络与稳定性）",
        "batch": 2,
        "section": "录制设置",
        "option": "是否强制启用https录制",
        "type": "bool",
        "default": False,
        "effect": "新增任务立即生效",
    },
    "disk_space_limit_gb": {
        "label": "空间阈值(GB)",
        "group": "第二批（网络与稳定性）",
        "batch": 2,
        "section": "录制设置",
        "option": "录制空间剩余阈值(gb)",
        "type": "float",
        "minimum": 0.0,
        "maximum": 10240.0,
        "default": 1.0,
        "effect": "新增任务立即生效",
    },
}

SETTINGS_FIELD_ORDER = tuple(SETTINGS_FIELD_DEFINITIONS.keys())


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
    max_request_workers: int = 3
    disk_space_limit_gb: float = 1.0
    probe_interval_seconds: float = 8.0
    use_proxy: bool = True
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
    """线程安全的 config.ini 读取与更新服务。"""

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
                    max_request_workers=self._read_int(
                        parser,
                        section="录制设置",
                        option="同一时间访问网络的线程数",
                        default=3,
                        minimum=1,
                        maximum=64,
                        warnings=warnings,
                    ),
                    disk_space_limit_gb=self._read_float(
                        parser,
                        section="录制设置",
                        option="录制空间剩余阈值(gb)",
                        default=1.0,
                        minimum=0.0,
                        maximum=10240.0,
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
                        default=True,
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
            except Exception as exc:  # pragma: no cover
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

    def get_settings_payload(self) -> dict:
        with self._lock:
            current_values = asdict(self._values)
            settings_values = {
                field_name: current_values.get(field_name)
                for field_name in SETTINGS_FIELD_ORDER
            }

            schema_items: list[dict[str, Any]] = []
            for field_name in SETTINGS_FIELD_ORDER:
                meta = SETTINGS_FIELD_DEFINITIONS[field_name]
                item = {
                    "field": field_name,
                    "label": meta["label"],
                    "group": meta["group"],
                    "batch": meta["batch"],
                    "type": meta["type"],
                    "default": meta["default"],
                    "effect": meta["effect"],
                }
                if "choices" in meta:
                    item["choices"] = list(meta["choices"])
                if "minimum" in meta:
                    item["minimum"] = meta["minimum"]
                if "maximum" in meta:
                    item["maximum"] = meta["maximum"]
                schema_items.append(item)

            return {
                "schema": schema_items,
                "values": settings_values,
                "last_reload": {
                    "success": self._last_result.success,
                    "changed": self._last_result.changed,
                    "reloaded_at": self._last_result.reloaded_at,
                    "config_mtime": self._last_result.config_mtime,
                    "warnings": list(self._last_result.warnings),
                    "error": self._last_result.error,
                },
            }

    def update_settings(self, fields: dict[str, Any]) -> dict:
        with self._lock:
            if not isinstance(fields, dict) or not fields:
                return {
                    "success": False,
                    "updated_fields": {},
                    "errors": {"_global": "fields 不能为空"},
                    "settings": self.get_settings_payload(),
                }

            normalized_fields: dict[str, Any] = {}
            errors: dict[str, str] = {}
            updated_flags: dict[str, bool] = {}

            for field_name, raw_value in fields.items():
                if field_name not in SETTINGS_FIELD_DEFINITIONS:
                    errors[field_name] = "字段不支持编辑"
                    updated_flags[field_name] = False
                    continue

                ok, value, error_message = self._normalize_setting_value(field_name, raw_value)
                if not ok:
                    errors[field_name] = error_message
                    updated_flags[field_name] = False
                    continue

                normalized_fields[field_name] = value
                updated_flags[field_name] = True

            if errors:
                return {
                    "success": False,
                    "updated_fields": updated_flags,
                    "errors": errors,
                    "settings": self.get_settings_payload(),
                }

            parser = configparser.RawConfigParser()
            parser.read(self._config_file_path, encoding=self._encoding)

            for field_name, value in normalized_fields.items():
                meta = SETTINGS_FIELD_DEFINITIONS[field_name]
                section = str(meta["section"])
                option = str(meta["option"])
                if not parser.has_section(section):
                    parser.add_section(section)
                parser.set(section, option, self._serialize_setting_value(field_name, value))

            try:
                with open(self._config_file_path, "w", encoding=self._encoding) as file:
                    parser.write(file)
            except Exception as exc:  # pragma: no cover
                return {
                    "success": False,
                    "updated_fields": {name: False for name in normalized_fields.keys()},
                    "errors": {"_global": f"写入配置失败: {exc}"},
                    "settings": self.get_settings_payload(),
                }

            reload_result = self.reload_if_needed(force=True)
            success = bool(reload_result.success)
            response_errors: dict[str, str] = {}
            if not success and reload_result.error:
                response_errors["_global"] = reload_result.error

            return {
                "success": success,
                "updated_fields": {name: success for name in normalized_fields.keys()},
                "errors": response_errors,
                "settings": self.get_settings_payload(),
                "snapshot": self.get_snapshot(mask_sensitive=True),
            }

    @classmethod
    def _normalize_setting_value(cls, field_name: str, raw_value: Any) -> tuple[bool, Any, str]:
        meta = SETTINGS_FIELD_DEFINITIONS[field_name]
        value_type = str(meta["type"])

        if value_type == "bool":
            if isinstance(raw_value, bool):
                return True, raw_value, ""
            if isinstance(raw_value, (int, float)):
                return True, bool(raw_value), ""
            mapping = {
                "是": True,
                "否": False,
                "true": True,
                "false": False,
                "1": True,
                "0": False,
                "yes": True,
                "no": False,
                "on": True,
                "off": False,
            }
            raw_key = str(raw_value).strip().lower()
            if raw_key in mapping:
                return True, mapping[raw_key], ""
            return False, None, "布尔值不合法"

        if value_type == "int":
            text_value = str(raw_value).strip()
            try:
                value = int(text_value)
            except Exception:
                try:
                    float_value = float(text_value)
                except Exception:
                    return False, None, "整数值不合法"
                if not float_value.is_integer():
                    return False, None, "整数值不合法"
                value = int(float_value)

            minimum = int(meta.get("minimum", value))
            maximum = int(meta.get("maximum", value))
            if value < minimum or value > maximum:
                return False, None, f"整数超出范围 [{minimum}, {maximum}]"
            return True, value, ""

        if value_type == "float":
            try:
                value = float(str(raw_value).strip())
            except Exception:
                return False, None, "浮点值不合法"

            minimum = float(meta.get("minimum", value))
            maximum = float(meta.get("maximum", value))
            if value < minimum or value > maximum:
                return False, None, f"浮点值超出范围 [{minimum}, {maximum}]"
            return True, value, ""

        if value_type == "enum":
            value = str(raw_value).strip()
            if meta.get("normalize_upper"):
                value = value.upper()
            choices = tuple(meta.get("choices", []))
            if value not in choices:
                return False, None, f"枚举值不合法，可选: {', '.join(choices)}"
            return True, value, ""

        if value_type == "string":
            return True, str(raw_value).strip(), ""

        return False, None, "字段类型不支持"

    @classmethod
    def _serialize_setting_value(cls, field_name: str, value: Any) -> str:
        meta = SETTINGS_FIELD_DEFINITIONS[field_name]
        value_type = str(meta["type"])

        if value_type == "bool":
            return "是" if bool(value) else "否"
        if value_type == "int":
            return str(int(value))
        if value_type == "float":
            return str(float(value))
        return str(value)

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
    def _read_float(
        parser: configparser.RawConfigParser,
        *,
        section: str,
        option: str,
        default: float,
        minimum: float,
        maximum: float,
        warnings: list[str],
    ) -> float:
        raw = RuntimeConfigService._read_value(parser, section=section, option=option, default=str(default))
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError):
            warnings.append(f"invalid float value at {section}.{option}: {raw!r}, fallback to {default}")
            return default

        clamped = max(minimum, min(maximum, value))
        if clamped != value:
            warnings.append(
                f"out-of-range float at {section}.{option}: {value}, clamped to [{minimum}, {maximum}] => {clamped}"
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
