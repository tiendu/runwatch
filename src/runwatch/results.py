from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Literal

Status = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class MetricSample:
    """One named metric sample emitted by a check.

    The check owns the metric's meaning. Exporters own its wire format.
    Metric names should follow Prometheus/OpenMetrics conventions and include
    a unit suffix where appropriate, such as ``_seconds`` or ``_ratio``.
    """

    name: str
    help: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    """Normalized output from every check.

    Checks return data only. Result sinks decide how to log or export it.
    """

    check_type: str
    name: str
    status: Status
    message: str
    duration_seconds: float
    observed_at: float = field(default_factory=time)
    labels: dict[str, str] = field(default_factory=dict)
    metrics: tuple[MetricSample, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def up(self) -> int:
        return 1 if self.status in {"ok", "warn"} else 0
