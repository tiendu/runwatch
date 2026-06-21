from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Callable
from threading import Event
from time import monotonic

from runwatch.checks import HttpCheck, SystemResourceCheck
from runwatch.config import RunwatchConfig
from runwatch.interfaces import Check, CheckRunner, ResultSink
from runwatch.logs import emit_json_event
from runwatch.main_support import execute_check
from runwatch.results import CheckResult
from runwatch.runner import SequentialCheckRunner, ThreadedCheckRunner
from runwatch.targets import LinuxTargetResolver, LinuxTargetSampler, TargetMonitor, TargetSpec

ResultCallback = Callable[[CheckResult], None]


def build_checks(config: RunwatchConfig) -> list[Check]:
    resolver = LinuxTargetResolver()
    sampler = LinuxTargetSampler()
    checks: list[Check] = []
    if config.system.enabled:
        checks.append(SystemResourceCheck(config.system))
    checks.extend(HttpCheck(item) for item in config.http)
    checks.extend(TargetMonitor(item, resolver, sampler) for item in config.targets)
    return checks


def dispatch_result(result: CheckResult, sinks: list[ResultSink]) -> None:
    for sink in sinks:
        sink.observe(result)


def exit_code_for(result: CheckResult) -> int:
    return {"ok": 0, "warn": 1, "fail": 2}[result.status]


def run_checks_once(
    checks: list[Check],
    sinks: list[ResultSink],
    runner: CheckRunner | None = None,
) -> int:
    exit_code = 0
    if runner is None:
        with SequentialCheckRunner() as sequential:
            for result in sequential.run(checks):
                dispatch_result(result, sinks)
                exit_code = max(exit_code, exit_code_for(result))
        return exit_code

    for result in runner.run(checks):
        dispatch_result(result, sinks)
        exit_code = max(exit_code, exit_code_for(result))
    return exit_code


def run_once(config: RunwatchConfig, sinks: list[ResultSink]) -> int:
    return run_checks_once(build_checks(config), sinks)


def sample_target_once(spec: TargetSpec, sample_seconds: float) -> CheckResult:
    monitor = TargetMonitor(spec, LinuxTargetResolver(), LinuxTargetSampler())
    first = execute_check(monitor)
    if first.status == "fail" or sample_seconds <= 0:
        return first
    Event().wait(sample_seconds)
    return execute_check(monitor)


def watch_target(
    spec: TargetSpec,
    interval_seconds: float,
    callback: ResultCallback,
    stop_event: Event | None = None,
) -> int:
    event = stop_event or Event()
    monitor = TargetMonitor(spec, LinuxTargetResolver(), LinuxTargetSampler())
    exit_code = 0

    while not event.is_set():
        result = execute_check(monitor)
        callback(result)
        exit_code = exit_code_for(result)
        if event.wait(interval_seconds):
            break
    return exit_code


def _install_signal_handlers(stop_event: Event) -> dict[int, object]:
    previous: dict[int, object] = {}

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    if not sys.platform.startswith("win"):
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, stop)
    return previous


def _restore_signal_handlers(previous: dict[int, object]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)  # type: ignore[arg-type]


def run_serve(
    config: RunwatchConfig,
    sinks: list[ResultSink],
    stop_event: Event | None = None,
) -> None:
    logger = logging.getLogger("runwatch")
    event = stop_event or Event()
    previous_handlers = _install_signal_handlers(event) if stop_event is None else {}
    checks = build_checks(config)

    try:
        with ThreadedCheckRunner(config.serve.max_workers) as runner:
            while not event.is_set():
                cycle_started = monotonic()
                run_checks_once(checks, sinks, runner)
                duration = monotonic() - cycle_started
                remaining = config.serve.interval_seconds - duration
                if remaining < 0:
                    emit_json_event(
                        logger,
                        level="warning",
                        event="cycle_overrun",
                        message="monitoring cycle exceeded its configured interval",
                        interval_seconds=config.serve.interval_seconds,
                        duration_seconds=round(duration, 6),
                    )
                    remaining = config.serve.interval_seconds
                event.wait(remaining)
    finally:
        if previous_handlers:
            _restore_signal_handlers(previous_handlers)
