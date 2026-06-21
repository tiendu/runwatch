from __future__ import annotations

from collections.abc import Sequence
from time import perf_counter

from runwatch.interfaces import Check, CheckRunner, ResultSink
from runwatch.results import CheckResult

_STATUS_EXIT_CODES = {
    "ok": 0,
    "warn": 1,
    "fail": 2,
}


def execute_check(check: Check) -> CheckResult:
    """Run one check without allowing a check failure to stop Runwatch."""

    started = perf_counter()
    try:
        return check.run()
    except Exception as exc:
        return CheckResult(
            check_type=check.check_type,
            name=check.name,
            status="fail",
            message=f"{type(exc).__name__}: {exc}",
            duration_seconds=perf_counter() - started,
            details={"exception_type": type(exc).__name__},
        )


def exit_code_for(result: CheckResult) -> int:
    """Map a normalized check status to a CLI exit code."""

    return _STATUS_EXIT_CODES[result.status]


def dispatch_result(result: CheckResult, sinks: Sequence[ResultSink]) -> None:
    """Send one result to each configured sink."""

    for sink in sinks:
        sink.observe(result)


def run_checks_once(
    checks: Sequence[Check],
    sinks: Sequence[ResultSink],
    runner: CheckRunner,
) -> int:
    """Execute one complete monitoring cycle with an explicitly owned runner."""

    exit_code = 0
    for result in runner.run(checks):
        dispatch_result(result, sinks)
        exit_code = max(exit_code, exit_code_for(result))
    return exit_code
