from __future__ import annotations

import logging
from collections.abc import Sequence
from threading import Event
from time import monotonic

from runwatch.check_factory import build_checks
from runwatch.config import RunwatchConfig
from runwatch.errors import ServiceError
from runwatch.execution import run_checks_once
from runwatch.exporters import OpenMetricsExporter
from runwatch.interfaces import ResultSink
from runwatch.logs import JsonResultLogger, emit_json_event, setup_logging
from runwatch.runner import ThreadedCheckRunner
from runwatch.signals import handle_shutdown_signals


def run_service_loop(
    config: RunwatchConfig,
    sinks: Sequence[ResultSink],
    stop_event: Event,
) -> None:
    """Run non-overlapping monitoring cycles until shutdown is requested.

    Shutdown prevents future cycles. Checks already running are allowed to
    finish, so every blocking check must enforce its own timeout.
    """

    logger = logging.getLogger("runwatch")
    checks = build_checks(config)
    if not checks:
        emit_json_event(
            logger,
            level="warning",
            event="no_checks_configured",
            message="no host, HTTP, or target checks are configured",
        )

    with ThreadedCheckRunner(config.serve.max_workers) as runner:
        while not stop_event.is_set():
            cycle_started = monotonic()

            run_checks_once(
                checks=checks,
                sinks=sinks,
                runner=runner,
            )

            duration = monotonic() - cycle_started
            remaining = config.serve.interval_seconds - duration

            if remaining <= 0:
                emit_json_event(
                    logger,
                    level="warning",
                    event="cycle_overrun",
                    message=("monitoring cycle exceeded its configured interval"),
                    interval_seconds=config.serve.interval_seconds,
                    duration_seconds=round(duration, 6),
                )
                remaining = config.serve.interval_seconds

            stop_event.wait(remaining)


def serve(
    config: RunwatchConfig,
    stop_event: Event | None = None,
) -> int:
    """Own the complete lifecycle of the persistent Runwatch service."""

    setup_logging()

    logger = logging.getLogger("runwatch")
    event = stop_event if stop_event is not None else Event()
    owns_signal_handlers = stop_event is None

    sinks: list[ResultSink] = [JsonResultLogger(logger)]
    exporter: OpenMetricsExporter | None = None

    try:
        if config.metrics.enabled:
            exporter = OpenMetricsExporter(config.metrics)
            try:
                exporter.start()
            except OSError as exc:
                raise ServiceError(
                    "cannot start metrics endpoint "
                    f"{config.metrics.address}:{config.metrics.port}: {exc}"
                ) from exc
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
            metrics_address=(config.metrics.address if config.metrics.enabled else None),
            metrics_port=(config.metrics.port if config.metrics.enabled else None),
        )

        if owns_signal_handlers:
            with handle_shutdown_signals(event):
                run_service_loop(config, sinks, event)
        else:
            run_service_loop(config, sinks, event)
    except Exception as exc:
        emit_json_event(
            logger,
            level="error",
            event="serve_failed",
            message="runwatch persistent monitor failed",
            exception_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    finally:
        try:
            if exporter is not None:
                exporter.stop()
        finally:
            emit_json_event(
                logger,
                level="info",
                event="serve_stopped",
                message="runwatch persistent monitor stopped",
            )

    return 0
