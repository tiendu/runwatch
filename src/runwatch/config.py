from __future__ import annotations

import json
import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from runwatch.defaults import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_METRICS_ADDRESS,
    DEFAULT_METRICS_PORT,
    DEFAULT_SERVE_INTERVAL_SECONDS,
)
from runwatch.errors import ConfigError
from runwatch.targets.models import TargetKind, TargetSpec


@dataclass(frozen=True)
class ServeConfig:
    interval_seconds: float = DEFAULT_SERVE_INTERVAL_SECONDS
    max_workers: int = DEFAULT_MAX_WORKERS


@dataclass(frozen=True)
class MetricsConfig:
    enabled: bool = True
    address: str = DEFAULT_METRICS_ADDRESS
    port: int = DEFAULT_METRICS_PORT
    include_runtime_metrics: bool = False


@dataclass(frozen=True)
class HttpCheckConfig:
    name: str
    url: str
    expected_status: int = 200
    timeout_seconds: float = 3.0
    retries: int = 2
    retry_delay_seconds: float = 1.0
    expected_body: str | None = None


@dataclass(frozen=True)
class SystemConfig:
    enabled: bool = True
    cpu_warn_percent: float = 80.0
    memory_warn_percent: float = 85.0
    disk_warn_percent: float = 90.0
    disk_paths: tuple[str, ...] = ("/",)


@dataclass(frozen=True)
class RunwatchConfig:
    serve: ServeConfig = field(default_factory=ServeConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    targets: tuple[TargetSpec, ...] = ()
    http: tuple[HttpCheckConfig, ...] = ()

    @property
    def agent(self) -> ServeConfig:
        """Compatibility alias for the original POC configuration API."""

        return self.serve


_ROOT_KEYS = {"serve", "agent", "metrics", "system", "targets", "http"}
_SERVE_KEYS = {"interval_seconds", "max_workers"}
_AGENT_KEYS = {"interval_seconds", "metrics_addr", "metrics_port"}
_METRICS_KEYS = {"enabled", "address", "port", "include_runtime_metrics"}
_SYSTEM_KEYS = {
    "enabled",
    "cpu_warn_percent",
    "memory_warn_percent",
    "disk_warn_percent",
    "disk_paths",
}
_TARGET_KEYS = {
    "name",
    "type",
    "value",
    "unit",
    "pid",
    "pid_file",
    "process",
    "target",
    "include_children",
}
_HTTP_KEYS = {
    "name",
    "url",
    "expected_status",
    "timeout_seconds",
    "retries",
    "retry_delay_seconds",
    "expected_body",
}
_TARGET_KINDS = {"auto", "systemd", "pid", "pid_file", "process"}


def _reject_unknown_keys(
    data: dict[str, Any],
    allowed: set[str],
    location: str,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        joined = ", ".join(repr(key) for key in unknown)
        raise ConfigError(f"{location} contains unknown key(s): {joined}")


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a TOML table")
    return value


def _array(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigError(f"[[{key}]] must be a TOML array of tables")
    return value


def _boolean(data: dict[str, Any], key: str, default: bool, location: str) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{location}.{key} must be a boolean")
    return value


def _integer(data: dict[str, Any], key: str, default: int, location: str) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{location}.{key} must be an integer")
    return value


def _number(data: dict[str, Any], key: str, default: float, location: str) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{location}.{key} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ConfigError(f"{location}.{key} must be finite")
    return parsed


def _string(data: dict[str, Any], key: str, default: str, location: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{location}.{key} must be a string")
    return value


def _optional_string(data: dict[str, Any], key: str, location: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{location}.{key} must be a string")
    return value


def _required_string(data: dict[str, Any], key: str, location: str) -> str:
    value = _optional_string(data, key, location)
    if value is None or not value.strip():
        raise ConfigError(f"{location}.{key} must be a non-empty string")
    return value.strip()


def _string_list(
    data: dict[str, Any],
    key: str,
    default: tuple[str, ...],
    location: str,
) -> tuple[str, ...]:
    value = data.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{location}.{key} must be an array of strings")
    return tuple(value)


def _target_from_raw(item: dict[str, Any], index: int) -> TargetSpec:
    location = f"targets[{index}]"
    _reject_unknown_keys(item, _TARGET_KEYS, location)

    name = _required_string(item, "name", location)
    kind_text = _string(item, "type", "auto", location)
    if kind_text not in _TARGET_KINDS:
        raise ConfigError(f"target {name!r} has unsupported type {kind_text!r}")
    kind = cast(TargetKind, kind_text)

    value = item.get("value")
    if value is None:
        value = {
            "systemd": item.get("unit"),
            "pid": item.get("pid"),
            "pid_file": item.get("pid_file"),
            "process": item.get("process"),
            "auto": item.get("target") or item.get("unit") or item.get("process"),
        }[kind]
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ConfigError(f"target {name!r} requires a string or integer value")

    text = str(value).strip()
    if not text:
        raise ConfigError(f"target {name!r} requires a non-empty value")
    if kind == "pid":
        try:
            pid = int(text)
        except ValueError as exc:
            raise ConfigError(f"target {name!r} PID must be an integer") from exc
        if pid <= 0:
            raise ConfigError(f"target {name!r} PID must be greater than zero")

    return TargetSpec(
        name=name,
        kind=kind,
        value=text,
        include_children=_boolean(item, "include_children", True, location),
    )


def _http_from_raw(item: dict[str, Any], index: int) -> HttpCheckConfig:
    location = f"http[{index}]"
    _reject_unknown_keys(item, _HTTP_KEYS, location)
    return HttpCheckConfig(
        name=_required_string(item, "name", location),
        url=_required_string(item, "url", location),
        expected_status=_integer(item, "expected_status", 200, location),
        timeout_seconds=_number(item, "timeout_seconds", 3.0, location),
        retries=_integer(item, "retries", 2, location),
        retry_delay_seconds=_number(item, "retry_delay_seconds", 1.0, location),
        expected_body=_optional_string(item, "expected_body", location),
    )


def validate_config(config: RunwatchConfig) -> RunwatchConfig:
    """Validate a fully constructed config and return it unchanged."""

    if not math.isfinite(config.serve.interval_seconds) or config.serve.interval_seconds <= 0:
        raise ConfigError("serve.interval_seconds must be a finite value greater than zero")
    if config.serve.max_workers <= 0:
        raise ConfigError("serve.max_workers must be greater than zero")

    if not config.metrics.address.strip():
        raise ConfigError("metrics.address must be a non-empty string")
    if config.metrics.address != config.metrics.address.strip():
        raise ConfigError("metrics.address must not contain leading or trailing whitespace")
    if not 1 <= config.metrics.port <= 65535:
        raise ConfigError("metrics.port must be between 1 and 65535")

    thresholds = {
        "system.cpu_warn_percent": config.system.cpu_warn_percent,
        "system.memory_warn_percent": config.system.memory_warn_percent,
        "system.disk_warn_percent": config.system.disk_warn_percent,
    }
    for name, value in thresholds.items():
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ConfigError(f"{name} must be a finite value between 0 and 100")

    if config.system.enabled and not config.system.disk_paths:
        raise ConfigError("system.disk_paths must contain at least one path")
    for path in config.system.disk_paths:
        if not path:
            raise ConfigError("system.disk_paths must not contain empty paths")
        if not Path(path).is_absolute():
            raise ConfigError(f"system disk path must be absolute: {path!r}")

    for target in config.targets:
        if not target.name.strip():
            raise ConfigError("target names must be non-empty")
        if target.kind not in _TARGET_KINDS:
            raise ConfigError(f"target {target.name!r} has unsupported type {target.kind!r}")
        if not target.value.strip():
            raise ConfigError(f"target {target.name!r} requires a non-empty value")
        if target.kind == "pid":
            try:
                pid = int(target.value)
            except ValueError as exc:
                raise ConfigError(f"target {target.name!r} PID must be an integer") from exc
            if pid <= 0:
                raise ConfigError(f"target {target.name!r} PID must be greater than zero")

    target_names = [target.name for target in config.targets]
    if len(target_names) != len(set(target_names)):
        raise ConfigError("target names must be unique")

    http_names = [check.name for check in config.http]
    if len(http_names) != len(set(http_names)):
        raise ConfigError("HTTP check names must be unique")

    for check in config.http:
        if not check.name.strip():
            raise ConfigError("HTTP check names must be non-empty")
        parsed = urlsplit(check.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError(f"HTTP check {check.name!r} URL must use http:// or https://")
        if not 100 <= check.expected_status <= 599:
            raise ConfigError(
                f"HTTP check {check.name!r} expected_status must be between 100 and 599"
            )
        if not math.isfinite(check.timeout_seconds) or check.timeout_seconds <= 0:
            raise ConfigError(
                f"HTTP check {check.name!r} timeout_seconds must be greater than zero"
            )
        if check.retries < 0:
            raise ConfigError(f"HTTP check {check.name!r} retries must be zero or greater")
        if not math.isfinite(check.retry_delay_seconds) or check.retry_delay_seconds < 0:
            raise ConfigError(
                f"HTTP check {check.name!r} retry_delay_seconds must be zero or greater"
            )

    return config


def _config_from_raw(raw: dict[str, Any]) -> RunwatchConfig:
    _reject_unknown_keys(raw, _ROOT_KEYS, "config")
    serve_raw = _table(raw, "serve")
    legacy_agent_raw = _table(raw, "agent")
    metrics_raw = _table(raw, "metrics")
    system_raw = _table(raw, "system")

    _reject_unknown_keys(serve_raw, _SERVE_KEYS, "serve")
    _reject_unknown_keys(legacy_agent_raw, _AGENT_KEYS, "agent")
    _reject_unknown_keys(metrics_raw, _METRICS_KEYS, "metrics")
    _reject_unknown_keys(system_raw, _SYSTEM_KEYS, "system")

    interval = (
        serve_raw["interval_seconds"]
        if "interval_seconds" in serve_raw
        else legacy_agent_raw.get("interval_seconds", DEFAULT_SERVE_INTERVAL_SECONDS)
    )
    metrics_address = (
        metrics_raw["address"]
        if "address" in metrics_raw
        else legacy_agent_raw.get("metrics_addr", DEFAULT_METRICS_ADDRESS)
    )
    metrics_port = (
        metrics_raw["port"]
        if "port" in metrics_raw
        else legacy_agent_raw.get("metrics_port", DEFAULT_METRICS_PORT)
    )

    # Validate inherited legacy values with the same strict helpers.
    combined_serve = dict(serve_raw)
    combined_serve["interval_seconds"] = interval
    combined_metrics = dict(metrics_raw)
    combined_metrics["address"] = metrics_address
    combined_metrics["port"] = metrics_port

    config = RunwatchConfig(
        serve=ServeConfig(
            interval_seconds=_number(
                combined_serve,
                "interval_seconds",
                DEFAULT_SERVE_INTERVAL_SECONDS,
                "serve",
            ),
            max_workers=_integer(serve_raw, "max_workers", DEFAULT_MAX_WORKERS, "serve"),
        ),
        metrics=MetricsConfig(
            enabled=_boolean(metrics_raw, "enabled", True, "metrics"),
            address=_string(
                combined_metrics,
                "address",
                DEFAULT_METRICS_ADDRESS,
                "metrics",
            ),
            port=_integer(combined_metrics, "port", DEFAULT_METRICS_PORT, "metrics"),
            include_runtime_metrics=_boolean(
                metrics_raw,
                "include_runtime_metrics",
                False,
                "metrics",
            ),
        ),
        system=SystemConfig(
            enabled=_boolean(system_raw, "enabled", True, "system"),
            cpu_warn_percent=_number(system_raw, "cpu_warn_percent", 80.0, "system"),
            memory_warn_percent=_number(
                system_raw,
                "memory_warn_percent",
                85.0,
                "system",
            ),
            disk_warn_percent=_number(system_raw, "disk_warn_percent", 90.0, "system"),
            disk_paths=_string_list(system_raw, "disk_paths", ("/",), "system"),
        ),
        targets=tuple(
            _target_from_raw(item, index)
            for index, item in enumerate(_array(raw, "targets"), start=1)
        ),
        http=tuple(
            _http_from_raw(item, index) for index, item in enumerate(_array(raw, "http"), start=1)
        ),
    )
    return validate_config(config)


def load_config_bytes(content: bytes, *, source: str = "<memory>") -> RunwatchConfig:
    """Parse and validate UTF-8 TOML bytes from a stable snapshot."""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"config {source} is not valid UTF-8: {exc}") from exc
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {source}: {exc}") from exc
    return _config_from_raw(raw)


def load_config(path: str | Path) -> RunwatchConfig:
    config_path = Path(path)
    try:
        content = config_path.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigError(f"config does not exist: {config_path}") from exc
    except PermissionError as exc:
        raise ConfigError(f"cannot read config {config_path}: permission denied") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read config {config_path}: {exc}") from exc
    return load_config_bytes(content, source=str(config_path))


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_config(config: RunwatchConfig) -> str:
    validate_config(config)
    lines = [
        "# runwatch persistent monitoring config",
        "",
        "[serve]",
        f"interval_seconds = {config.serve.interval_seconds:g}",
        f"max_workers = {config.serve.max_workers}",
        "",
        "[metrics]",
        f"enabled = {str(config.metrics.enabled).lower()}",
        f"address = {_toml_string(config.metrics.address)}",
        f"port = {config.metrics.port}",
        f"include_runtime_metrics = {str(config.metrics.include_runtime_metrics).lower()}",
        "",
        "[system]",
        f"enabled = {str(config.system.enabled).lower()}",
        f"cpu_warn_percent = {config.system.cpu_warn_percent:g}",
        f"memory_warn_percent = {config.system.memory_warn_percent:g}",
        f"disk_warn_percent = {config.system.disk_warn_percent:g}",
        "disk_paths = [" + ", ".join(_toml_string(path) for path in config.system.disk_paths) + "]",
    ]

    for target in config.targets:
        lines.extend(
            [
                "",
                "[[targets]]",
                f"name = {_toml_string(target.name)}",
                f"type = {_toml_string(target.kind)}",
                f"value = {_toml_string(target.value)}",
                f"include_children = {str(target.include_children).lower()}",
            ]
        )

    for http in config.http:
        lines.extend(
            [
                "",
                "[[http]]",
                f"name = {_toml_string(http.name)}",
                f"url = {_toml_string(http.url)}",
                f"expected_status = {http.expected_status}",
                f"timeout_seconds = {http.timeout_seconds:g}",
                f"retries = {http.retries}",
                f"retry_delay_seconds = {http.retry_delay_seconds:g}",
            ]
        )
        if http.expected_body is not None:
            lines.append(f"expected_body = {_toml_string(http.expected_body)}")

    return "\n".join(lines) + "\n"


DEFAULT_CONFIG = render_config(
    RunwatchConfig(
        targets=(
            TargetSpec(
                name="example",
                kind="auto",
                value="replace-me",
                include_children=True,
            ),
        )
    )
).replace(
    '[[targets]]\nname = "example"\ntype = "auto"\nvalue = "replace-me"\ninclude_children = true\n',
    "# Add targets with `runwatch setup`, or uncomment and edit:\n#\n"
    '# [[targets]]\n# name = "nginx"\n# type = "systemd"\n'
    '# value = "nginx.service"\n# include_children = true\n',
)
