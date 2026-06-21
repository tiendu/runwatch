from __future__ import annotations

import logging
from collections.abc import Sequence
from threading import Event
from time import monotonic

from runwatch.check_factory import build_checks
from runwatch.config import RunwatchConfig
from runwatch.execution import run_checks_once
from runwatch.exporters import OpenMetricsExporter
from runwatch.interfaces import ResultSink
from runwatch.logs import JsonResultLogger, emit_json_event, setup_logging
from runwatch.runner import ThreadedCheckRunner
from runwatch.signals import shutdown_signals


def run_service_loop(
    config: RunwatchConfig,
    sinks: Sequence[ResultSink],
    stop_event: Event,
) -> None:
    """Run non-overlapping monitoring cycles until shutdown is requested."""

    logger = logging.getLogger("runwatch")
    checks = build_checks(config)

    with ThreadedCheckRunner(config.serve.max_workers) as runner:
        while not stop_event.is_set():
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

            stop_event.wait(remaining)


def serve(config: RunwatchConfig, stop_event: Event | None = None) -> int:
    """Own the complete lifecycle of the persistent Runwatch service."""

    setup_logging()
    logger = logging.getLogger("runwatch")
    event = stop_event or Event()
    sinks: list[ResultSink] = [JsonResultLogger(logger)]
    exporter: OpenMetricsExporter | None = None

    if config.metrics.enabled:
        exporter = OpenMetricsExporter(config.metrics)
        exporter.start()
        sinks.append(exporter)

    emit_json_event(
        logger,
        level="info",
        event="serve_started",
        message="runwatch persistent monitor started",
        target_count=len(config.targets),
        http_check_count=len(config.http),
        host_metrics_enabled=config.system.enabled,
        max_workers=config.serve.max_workers,
        interval_seconds=config.serve.interval_seconds,
        metrics_enabled=config.metrics.enabled,
        metrics_address=config.metrics.address if config.metrics.enabled else None,
        metrics_port=config.metrics.port if config.metrics.enabled else None,
    )

    try:
        if stop_event is None:
            with shutdown_signals(event):
                run_service_loop(config, sinks, event)
        else:
            run_service_loop(config, sinks, event)
    finally:
        if exporter is not None:
            exporter.stop()
        emit_json_event(
            logger,
            level="info",
            event="serve_stopped",
            message="runwatch persistent monitor stopped",
        )

    return 0
