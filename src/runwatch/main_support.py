from __future__ import annotations

from time import perf_counter

from runwatch.interfaces import Check
from runwatch.results import CheckResult


def execute_check(check: Check) -> CheckResult:
    """Run one check without allowing a plugin/check bug to stop the monitor."""

    started = perf_counter()
    try:
        return check.run()
    except Exception as exc:
        return CheckResult(
            check_type=check.check_type,
            name=check.name,
            status="fail",
            message=f"{exc.__class__.__name__}: {exc}",
            duration_seconds=perf_counter() - started,
            details={"exception_type": exc.__class__.__name__},
        )
