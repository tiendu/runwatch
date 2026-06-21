from threading import Event

from runwatch.config import MetricsConfig, RunwatchConfig, SystemConfig
from runwatch.service import serve


def test_serve_with_external_stop_event_exits_cleanly() -> None:
    stopped = Event()
    stopped.set()
    config = RunwatchConfig(
        metrics=MetricsConfig(enabled=False),
        system=SystemConfig(enabled=False),
    )

    assert serve(config, stop_event=stopped) == 0
