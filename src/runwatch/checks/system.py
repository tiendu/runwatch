from __future__ import annotations

from time import perf_counter

import psutil

from runwatch.config import SystemConfig
from runwatch.results import CheckResult, MetricSample, Status


class SystemResourceCheck:
    check_type = "system"
    name = "host"

    def __init__(self, config: SystemConfig) -> None:
        self.config = config

    def run(self) -> CheckResult:
        started = perf_counter()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_percent = psutil.virtual_memory().percent
        disk_percent: dict[str, float] = {}
        disk_errors: dict[str, str] = {}

        for path in self.config.disk_paths:
            try:
                disk_percent[path] = psutil.disk_usage(path).percent
            except OSError as exc:
                disk_errors[path] = f"{exc.__class__.__name__}: {exc}"

        warnings: list[str] = []
        if cpu_percent >= self.config.cpu_warn_percent:
            warnings.append(f"cpu {cpu_percent:.1f}%")
        if memory_percent >= self.config.memory_warn_percent:
            warnings.append(f"memory {memory_percent:.1f}%")
        for path, used_percent in disk_percent.items():
            if used_percent >= self.config.disk_warn_percent:
                warnings.append(f"disk {path} {used_percent:.1f}%")

        metrics = [
            MetricSample(
                name="runwatch_system_cpu_usage_ratio",
                help="Host CPU usage as a ratio from 0 to 1.",
                value=cpu_percent / 100.0,
            ),
            MetricSample(
                name="runwatch_system_memory_usage_ratio",
                help="Host memory usage as a ratio from 0 to 1.",
                value=memory_percent / 100.0,
            ),
        ]
        metrics.extend(
            MetricSample(
                name="runwatch_system_disk_usage_ratio",
                help="Filesystem usage as a ratio from 0 to 1.",
                value=used_percent / 100.0,
                labels={"path": path},
            )
            for path, used_percent in disk_percent.items()
        )

        status: Status
        if disk_errors:
            status = "fail"
            message = ", ".join(f"disk {path}: {error}" for path, error in disk_errors.items())
        elif warnings:
            status = "warn"
            message = ", ".join(warnings)
        else:
            status = "ok"
            message = "system resources ok"

        return CheckResult(
            check_type=self.check_type,
            name=self.name,
            status=status,
            message=message,
            duration_seconds=perf_counter() - started,
            metrics=tuple(metrics),
            details={"disk_percent": disk_percent, "disk_errors": disk_errors},
        )
