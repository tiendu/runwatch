from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from runwatch.templates.systemd import SystemdUnitTemplate


def install_systemd_service(
    *,
    executable: str,
    config_source: Path,
    config_path: Path = Path("/etc/runwatch/runwatch.toml"),
    unit_path: Path = Path("/etc/systemd/system/runwatch.service"),
    enable: bool = True,
    force_unit: bool = True,
    force_config: bool = False,
    dry_run: bool = False,
) -> None:
    if os.geteuid() != 0 and not dry_run:
        raise PermissionError("systemd installation must run as root")

    unit = SystemdUnitTemplate(
        config_path=str(config_path),
        executable=executable,
    ).render()

    if dry_run:
        print(f"# would copy {config_source} to {config_path}")
        print(f"# would write {unit_path}")
        print(unit)
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists() or force_config:
        temporary = config_path.with_suffix(config_path.suffix + ".tmp")
        shutil.copyfile(config_source, temporary)
        temporary.chmod(0o640)
        temporary.replace(config_path)
    else:
        print(f"kept existing {config_path}")

    if unit_path.exists() and not force_unit:
        raise FileExistsError(f"refusing to overwrite existing unit: {unit_path}")
    unit_path.write_text(unit, encoding="utf-8")
    unit_path.chmod(0o644)

    Path("/var/lib/runwatch").mkdir(parents=True, exist_ok=True)
    Path("/var/log/runwatch").mkdir(parents=True, exist_ok=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    if enable:
        subprocess.run(["systemctl", "enable", "--now", unit_path.name], check=True)


__all__ = ["install_systemd_service"]
