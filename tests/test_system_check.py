from runwatch.checks.system import SystemResourceCheck
from runwatch.config import SystemConfig


def test_system_check_emits_ratio_metrics() -> None:
    result = SystemResourceCheck(SystemConfig(disk_paths=("/",))).run()
    metrics = {sample.name: sample for sample in result.metrics if not sample.labels}
    disk = next(
        sample for sample in result.metrics if sample.name == "runwatch_system_disk_usage_ratio"
    )

    assert 0.0 <= metrics["runwatch_system_cpu_usage_ratio"].value <= 1.0
    assert 0.0 <= metrics["runwatch_system_memory_usage_ratio"].value <= 1.0
    assert 0.0 <= disk.value <= 1.0
    assert disk.labels == {"path": "/"}
