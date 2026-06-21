from __future__ import annotations

from collections.abc import Callable
from threading import Event
from time import sleep

from runwatch.execution import execute_check, exit_code_for
from runwatch.results import CheckResult
from runwatch.targets import LinuxTargetResolver, LinuxTargetSampler, TargetMonitor, TargetSpec

ResultCallback = Callable[[CheckResult], None]


def create_target_monitor(spec: TargetSpec) -> TargetMonitor:
    """Construct a monitor for one ad-hoc target."""

    return TargetMonitor(
        spec,
        resolver=LinuxTargetResolver(),
        sampler=LinuxTargetSampler(),
    )


def sample_target_once(spec: TargetSpec, sample_seconds: float) -> CheckResult:
    """Resolve and sample one target, using two samples when rates are requested."""

    monitor = create_target_monitor(spec)
    initial = execute_check(monitor)
    if initial.status == "fail" or sample_seconds <= 0:
        return initial

    sleep(sample_seconds)
    return execute_check(monitor)


def watch_target(
    spec: TargetSpec,
    interval_seconds: float,
    callback: ResultCallback,
    stop_event: Event | None = None,
) -> int:
    """Continuously sample one target until interrupted."""

    event = stop_event or Event()
    monitor = create_target_monitor(spec)
    last_exit_code = 0

    while not event.is_set():
        result = execute_check(monitor)
        callback(result)
        last_exit_code = exit_code_for(result)
        if event.wait(interval_seconds):
            break

    return last_exit_code
