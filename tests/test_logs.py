import json
import logging

from runwatch.logs import JsonResultLogger
from runwatch.results import CheckResult


def test_failed_result_uses_error_log_level(caplog: object) -> None:
    logger = logging.getLogger("runwatch-test")
    sink = JsonResultLogger(logger)

    # pytest's caplog fixture is intentionally accessed through its public API,
    # but kept untyped here to avoid adding pytest plugin types to production.
    caplog.set_level(logging.INFO, logger="runwatch-test")  # type: ignore[attr-defined]
    sink.observe(
        CheckResult(
            check_type="http",
            name="api",
            status="fail",
            message="connection refused",
            duration_seconds=0.1,
        )
    )

    record = caplog.records[-1]  # type: ignore[attr-defined]
    payload = json.loads(record.message)
    assert record.levelno == logging.ERROR
    assert payload["event"] == "check_result"
    assert payload["level"] == "error"
