from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemdUnitTemplate:
    config_path: str = "/etc/runwatch/runwatch.toml"
    executable: str = "/usr/local/bin/runwatch"

    def render(self) -> str:
        return f"""[Unit]
Description=runwatch service and process monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Environment=PYTHONUNBUFFERED=1
ExecStart={self.executable} serve --config {self.config_path}
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/runwatch /var/log/runwatch

[Install]
WantedBy=multi-user.target
"""
