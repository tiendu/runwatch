from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    GCCollector,
    Gauge,
    PlatformCollector,
    ProcessCollector,
    start_http_server,
)

from runwatch.config import MetricsConfig
from runwatch.results import CheckResult, MetricSample


@dataclass(frozen=True)
class _MetricDefinition:
    help: str
    label_names: tuple[str, ...]


class OpenMetricsExporter:
    """Prometheus/OpenMetrics-compatible result sink.

    The exporter always provides universal check health metrics. Individual
    checks can additionally emit named metric families through MetricSample.
    """

    def __init__(self, config: MetricsConfig) -> None:
        self.config = config
        self.registry = CollectorRegistry()
        self._started = False
        self._server: Any | None = None
        self._thread: Any | None = None
        self._metric_definitions: dict[str, _MetricDefinition] = {}
        self._metric_gauges: dict[str, Gauge] = {}
        self._series_by_check: dict[
            tuple[str, str], set[tuple[str, tuple[tuple[str, str], ...]]]
        ] = {}

        if config.include_runtime_metrics:
            GCCollector(registry=self.registry)
            PlatformCollector(registry=self.registry)
            ProcessCollector(registry=self.registry)

        self._up = Gauge(
            "runwatch_check_up",
            "Whether a runwatch check is healthy: 1 for ok or warn, 0 for fail.",
            ["check_type", "name"],
            registry=self.registry,
        )
        self._status = Gauge(
            "runwatch_check_status",
            "Check status encoded as ok=0, warn=1, fail=2.",
            ["check_type", "name"],
            registry=self.registry,
        )
        self._duration = Gauge(
            "runwatch_check_duration_seconds",
            "Duration of the complete check execution in seconds.",
            ["check_type", "name"],
            registry=self.registry,
        )
        self._last_run = Gauge(
            "runwatch_check_last_run_timestamp_seconds",
            "Unix timestamp of the most recent check result.",
            ["check_type", "name"],
            registry=self.registry,
        )

    def start(self) -> None:
        if self._started or not self.config.enabled:
            return
        self._server, self._thread = start_http_server(
            self.config.port,
            addr=self.config.address,
            registry=self.registry,
        )
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._started = False

    def _gauge_for(self, sample: MetricSample) -> Gauge:
        label_names = tuple(sorted(sample.labels))
        definition = _MetricDefinition(help=sample.help, label_names=label_names)
        existing = self._metric_definitions.get(sample.name)
        if existing is not None and existing != definition:
            raise ValueError(
                f"metric {sample.name!r} changed definition: expected {existing}, got {definition}"
            )

        gauge = self._metric_gauges.get(sample.name)
        if gauge is None:
            gauge = Gauge(
                sample.name,
                sample.help,
                label_names,
                registry=self.registry,
            )
            self._metric_definitions[sample.name] = definition
            self._metric_gauges[sample.name] = gauge
        return gauge

    def _observe_sample(self, sample: MetricSample) -> None:
        gauge = self._gauge_for(sample)
        if sample.labels:
            gauge.labels(**sample.labels).set(sample.value)
        else:
            gauge.set(sample.value)

    def _remove_stale_series(self, result: CheckResult) -> None:
        check_key = (result.check_type, result.name)
        current = {(sample.name, tuple(sorted(sample.labels.items()))) for sample in result.metrics}
        previous = self._series_by_check.get(check_key, set())
        for metric_name, label_items in previous - current:
            gauge = self._metric_gauges.get(metric_name)
            definition = self._metric_definitions.get(metric_name)
            if gauge is None or definition is None or not definition.label_names:
                continue
            labels = dict(label_items)
            gauge.remove(*(labels[name] for name in definition.label_names))
        self._series_by_check[check_key] = current

    def observe(self, result: CheckResult) -> None:
        self._up.labels(result.check_type, result.name).set(result.up)
        self._status.labels(result.check_type, result.name).set(
            {"ok": 0, "warn": 1, "fail": 2}[result.status]
        )
        self._duration.labels(result.check_type, result.name).set(result.duration_seconds)
        self._last_run.labels(result.check_type, result.name).set(result.observed_at)
        self._remove_stale_series(result)
        for sample in result.metrics:
            self._observe_sample(sample)
