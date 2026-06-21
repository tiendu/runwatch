from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from runwatch.results import CheckResult

LogLevel = Literal["info", "warning", "error"]


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def emit_json_event(
    logger: logging.Logger,
    *,
    level: LogLevel,
    event: str,
    message: str,
    **fields: Any,
) -> None:
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        "message": message,
        **fields,
    }
    log_method = {
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
    }[level]
    log_method(json.dumps(payload, separators=(",", ":"), sort_keys=True))


class JsonResultLogger:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("runwatch")

    def observe(self, result: CheckResult) -> None:
        level: LogLevel = (
            "error" if result.status == "fail" else "warning" if result.status == "warn" else "info"
        )
        metrics = [
            {
                "name": sample.name,
                "value": sample.value,
                "labels": sample.labels,
            }
            for sample in result.metrics
        ]
        emit_json_event(
            self.logger,
            level=level,
            event="check_result",
            message=result.message,
            observed_at=datetime.fromtimestamp(result.observed_at, tz=timezone.utc).isoformat(),
            check_type=result.check_type,
            name=result.name,
            status=result.status,
            duration_seconds=round(result.duration_seconds, 6),
            labels=result.labels,
            metrics=metrics,
            details=result.details,
        )
