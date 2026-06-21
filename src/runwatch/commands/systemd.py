from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from runwatch.errors import InstallationError
from runwatch.installation import install_systemd_service


def handle_install_systemd(args: argparse.Namespace) -> int:
    executable = args.executable or shutil.which("runwatch") or "/usr/local/bin/runwatch"
    source = Path(args.config_source)
    if not source.is_file():
        raise InstallationError(f"config source does not exist: {source}")

    install_systemd_service(
        executable=executable,
        config_source=source,
        config_path=Path(args.config_path),
        unit_path=Path(args.unit_path),
        enable=args.enable,
        force_unit=args.force,
        force_config=args.force_config,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        print("installed runwatch systemd service")
    return 0
