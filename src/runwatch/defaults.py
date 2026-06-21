from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/etc/runwatch/runwatch.toml")
DEFAULT_UNIT_PATH = Path("/etc/systemd/system/runwatch.service")
DEFAULT_LOCAL_CONFIG_PATH = Path("runwatch.toml")
DEFAULT_METRICS_ADDRESS = "127.0.0.1"
DEFAULT_METRICS_PORT = 9109
DEFAULT_SAMPLE_SECONDS = 1.0
DEFAULT_WATCH_INTERVAL_SECONDS = 2.0
DEFAULT_SERVE_INTERVAL_SECONDS = 30.0
DEFAULT_MAX_WORKERS = 4
