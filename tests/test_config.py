from pathlib import Path

from runwatch.config import load_config, render_config
from runwatch.targets import TargetSpec

ROOT = Path(__file__).parents[1]


def test_load_safe_example_config() -> None:
    config = load_config(ROOT / "examples" / "runwatch.toml")

    assert config.serve.interval_seconds == 30
    assert config.serve.max_workers == 4
    assert config.metrics.address == "127.0.0.1"
    assert config.metrics.port == 9109
    assert config.metrics.include_runtime_metrics is False
    assert config.http == ()
    assert config.targets == ()


def test_load_legacy_agent_metrics_keys(tmp_path: Path) -> None:
    path = tmp_path / "legacy.toml"
    path.write_text(
        """
[agent]
interval_seconds = 10
metrics_addr = "0.0.0.0"
metrics_port = 9200

[system]
disk_paths = ["/"]
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.serve.interval_seconds == 10
    assert config.metrics.address == "0.0.0.0"
    assert config.metrics.port == 9200


def test_target_round_trip(tmp_path: Path) -> None:
    from runwatch.config import RunwatchConfig

    config = RunwatchConfig(
        targets=(TargetSpec(name="nginx", kind="systemd", value="nginx.service"),)
    )
    path = tmp_path / "runwatch.toml"
    path.write_text(render_config(config), encoding="utf-8")

    loaded = load_config(path)

    assert loaded.targets == config.targets
