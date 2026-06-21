from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from runwatch.commands.common import write_text_atomic
from runwatch.templates import (
    DemoComposeTemplate,
    PrometheusAlertsTemplate,
    PrometheusScrapeTemplate,
    SystemdUnitTemplate,
)


def _emit_or_write(content: str, output: str | None, *, overwrite: bool) -> None:
    if output:
        write_text_atomic(Path(output), content, overwrite=overwrite)
    else:
        print(content)


def handle_gen_systemd(args: argparse.Namespace) -> int:
    executable = args.executable or shutil.which("runwatch") or "/usr/local/bin/runwatch"
    content = SystemdUnitTemplate(
        config_path=args.config_path,
        executable=executable,
    ).render()
    _emit_or_write(content, args.output, overwrite=args.force)
    return 0


def handle_gen_prometheus(args: argparse.Namespace) -> int:
    content = PrometheusScrapeTemplate(host=args.host, port=args.port).render()
    _emit_or_write(content, args.output, overwrite=args.force)
    return 0


def handle_gen_alerts(args: argparse.Namespace) -> int:
    _emit_or_write(PrometheusAlertsTemplate().render(), args.output, overwrite=args.force)
    return 0


def handle_gen_compose(args: argparse.Namespace) -> int:
    _emit_or_write(DemoComposeTemplate().render(), args.output, overwrite=args.force)
    return 0
