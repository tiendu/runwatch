from prometheus_client import generate_latest

from runwatch.config import MetricsConfig
from runwatch.exporters import OpenMetricsExporter
from runwatch.results import CheckResult, MetricSample


def test_exporter_uses_named_metric_families() -> None:
    exporter = OpenMetricsExporter(MetricsConfig(include_runtime_metrics=False))
    exporter.observe(
        CheckResult(
            check_type="system",
            name="host",
            status="ok",
            message="ok",
            duration_seconds=0.125,
            observed_at=1234.0,
            metrics=(
                MetricSample(
                    name="runwatch_system_cpu_usage_ratio",
                    help="Host CPU usage ratio.",
                    value=0.25,
                ),
                MetricSample(
                    name="runwatch_system_disk_usage_ratio",
                    help="Filesystem usage ratio.",
                    value=0.5,
                    labels={"path": "/"},
                ),
            ),
        )
    )

    payload = generate_latest(exporter.registry).decode()

    assert 'runwatch_check_up{check_type="system",name="host"} 1.0' in payload
    assert 'runwatch_check_duration_seconds{check_type="system",name="host"} 0.125' in payload
    assert "runwatch_system_cpu_usage_ratio 0.25" in payload
    assert 'runwatch_system_disk_usage_ratio{path="/"} 0.5' in payload
    assert "runwatch_metric_value" not in payload
    assert "python_gc_objects_collected_total" not in payload


def test_runtime_metrics_can_be_enabled() -> None:
    exporter = OpenMetricsExporter(MetricsConfig(include_runtime_metrics=True))

    payload = generate_latest(exporter.registry).decode()

    assert "python_info" in payload
    assert "process_resident_memory_bytes" in payload


def test_exporter_removes_stale_labeled_series() -> None:
    exporter = OpenMetricsExporter(MetricsConfig(include_runtime_metrics=False))
    first = CheckResult(
        check_type="target",
        name="api",
        status="ok",
        message="ok",
        duration_seconds=0.1,
        metrics=(
            MetricSample(
                name="runwatch_target_connections",
                help="Connections by state.",
                value=3.0,
                labels={"name": "api", "state": "established"},
            ),
        ),
    )
    second = CheckResult(
        check_type="target",
        name="api",
        status="ok",
        message="ok",
        duration_seconds=0.1,
        metrics=(),
    )

    exporter.observe(first)
    exporter.observe(second)
    payload = generate_latest(exporter.registry).decode()

    assert 'state="established"' not in payload
