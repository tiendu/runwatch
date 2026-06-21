from __future__ import annotations

import re
from dataclasses import dataclass

from runwatch.defaults import DEFAULT_CONFIG_PATH
from runwatch.errors import TemplateError

_SAFE_ARGUMENT = re.compile(r"^[A-Za-z0-9_./:@+,-]+$")


def _quote_argument(value: str) -> str:
    if not value or "\n" in value or "\r" in value or "\x00" in value:
        raise TemplateError("systemd command arguments must be non-empty single-line strings")
    if _SAFE_ARGUMENT.fullmatch(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class SystemdUnitTemplate:
    config_path: str = str(DEFAULT_CONFIG_PATH)
    executable: str = "/usr/local/bin/runwatch"

    def render(self) -> str:
        executable = _quote_argument(self.executable)
        config_path = _quote_argument(self.config_path)
        return f"""[Unit]
Description=runwatch service and process monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Environment=PYTHONUNBUFFERED=1
ExecStart={executable} serve --config {config_path}
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

NoNewPrivileges=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
"""
