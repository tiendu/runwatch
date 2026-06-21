from __future__ import annotations

from runwatch.checks import HttpCheck, SystemResourceCheck
from runwatch.config import RunwatchConfig
from runwatch.interfaces import Check
from runwatch.targets import LinuxTargetResolver, LinuxTargetSampler, TargetMonitor


def build_checks(config: RunwatchConfig) -> list[Check]:
    """Build independent checks from persistent configuration."""

    checks: list[Check] = []

    if config.system.enabled:
        checks.append(SystemResourceCheck(config.system))

    checks.extend(HttpCheck(item) for item in config.http)

    for target in config.targets:
        checks.append(
            TargetMonitor(
                target,
                resolver=LinuxTargetResolver(),
                sampler=LinuxTargetSampler(),
            )
        )

    return checks
