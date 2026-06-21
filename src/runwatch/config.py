from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runwatch.targets.models import TargetSpec


@dataclass(frozen=True)
class ServeConfig:
    interval_seconds: float = 30.0
    max_workers: int = 4


@dataclass(frozen=True)
class MetricsConfig:
    enabled: bool = True
    address: str = "127.0.0.1"
    port: int = 9109
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


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{key}] must be a TOML table")
    return value


def _array(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"[[{key}]] must be a TOML array of tables")
    return value


def _target_from_raw(item: dict[str, Any]) -> TargetSpec:
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("every [[targets]] entry requires a non-empty name")

    kind = str(item.get("type", "auto"))
    if kind not in {"auto", "systemd", "pid", "pid_file", "process"}:
        raise ValueError(f"target {name!r} has unsupported type {kind!r}")

    value = item.get("value")
    if value is None:
        value = {
            "systemd": item.get("unit"),
            "pid": item.get("pid"),
            "pid_file": item.get("pid_file"),
            "process": item.get("process"),
            "auto": item.get("target") or item.get("unit") or item.get("process"),
        }[kind]
    if value is None or str(value).strip() == "":
        raise ValueError(f"target {name!r} requires a value")

    return TargetSpec(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        value=str(value),
        include_children=bool(item.get("include_children", True)),
    )


def _validate(config: RunwatchConfig) -> RunwatchConfig:
    if config.serve.interval_seconds <= 0:
        raise ValueError("serve.interval_seconds must be greater than zero")
    if config.serve.max_workers <= 0:
        raise ValueError("serve.max_workers must be greater than zero")
    if not 1 <= config.metrics.port <= 65535:
        raise ValueError("metrics.port must be between 1 and 65535")
    if config.system.enabled and not config.system.disk_paths:
        raise ValueError("system.disk_paths must contain at least one path")
    names = [target.name for target in config.targets]
    if len(names) != len(set(names)):
        raise ValueError("target names must be unique")
    return config


def load_config(path: str | Path) -> RunwatchConfig:
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)

    serve_raw = _table(raw, "serve")
    legacy_agent_raw = _table(raw, "agent")
    metrics_raw = _table(raw, "metrics")
    system_raw = _table(raw, "system")

    # Preserve readability of the original POC's [agent] table.
    interval = serve_raw.get("interval_seconds", legacy_agent_raw.get("interval_seconds", 30.0))
    metrics_address = metrics_raw.get("address", legacy_agent_raw.get("metrics_addr", "127.0.0.1"))
    metrics_port = metrics_raw.get("port", legacy_agent_raw.get("metrics_port", 9109))

    config = RunwatchConfig(
        serve=ServeConfig(
            interval_seconds=float(interval),
            max_workers=int(serve_raw.get("max_workers", 4)),
        ),
        metrics=MetricsConfig(
            enabled=bool(metrics_raw.get("enabled", True)),
            address=str(metrics_address),
            port=int(metrics_port),
            include_runtime_metrics=bool(metrics_raw.get("include_runtime_metrics", False)),
        ),
        system=SystemConfig(
            enabled=bool(system_raw.get("enabled", True)),
            cpu_warn_percent=float(system_raw.get("cpu_warn_percent", 80.0)),
            memory_warn_percent=float(system_raw.get("memory_warn_percent", 85.0)),
            disk_warn_percent=float(system_raw.get("disk_warn_percent", 90.0)),
            disk_paths=tuple(str(path) for path in system_raw.get("disk_paths", ["/"])),
        ),
        targets=tuple(_target_from_raw(item) for item in _array(raw, "targets")),
        http=tuple(HttpCheckConfig(**item) for item in _array(raw, "http")),
    )
    return _validate(config)


def render_config(config: RunwatchConfig) -> str:
    lines = [
        "# runwatch persistent monitoring config",
        "",
        "[serve]",
        f"interval_seconds = {config.serve.interval_seconds:g}",
        f"max_workers = {config.serve.max_workers}",
        "",
        "[metrics]",
        f"enabled = {str(config.metrics.enabled).lower()}",
        f'address = "{config.metrics.address}"',
        f"port = {config.metrics.port}",
        f"include_runtime_metrics = {str(config.metrics.include_runtime_metrics).lower()}",
        "",
        "[system]",
        f"enabled = {str(config.system.enabled).lower()}",
        f"cpu_warn_percent = {config.system.cpu_warn_percent:g}",
        f"memory_warn_percent = {config.system.memory_warn_percent:g}",
        f"disk_warn_percent = {config.system.disk_warn_percent:g}",
        "disk_paths = [" + ", ".join(f'"{path}"' for path in config.system.disk_paths) + "]",
    ]

    for target in config.targets:
        lines.extend(
            [
                "",
                "[[targets]]",
                f'name = "{target.name}"',
                f'type = "{target.kind}"',
                f'value = "{target.value}"',
                f"include_children = {str(target.include_children).lower()}",
            ]
        )

    for http in config.http:
        lines.extend(
            [
                "",
                "[[http]]",
                f'name = "{http.name}"',
                f'url = "{http.url}"',
                f"expected_status = {http.expected_status}",
                f"timeout_seconds = {http.timeout_seconds:g}",
                f"retries = {http.retries}",
                f"retry_delay_seconds = {http.retry_delay_seconds:g}",
            ]
        )
        if http.expected_body is not None:
            lines.append(f'expected_body = "{http.expected_body}"')

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
    '# Add targets with `runwatch setup`, or uncomment and edit:\n#\n# [[targets]]\n# name = "nginx"\n# type = "systemd"\n# value = "nginx.service"\n# include_children = true\n',
)
