from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from runwatch.config import (
    MetricsConfig,
    RunwatchConfig,
    ServeConfig,
    render_config,
    validate_config,
)
from runwatch.errors import UsageError
from runwatch.filesystem import write_text_atomic
from runwatch.installation import install_systemd_service
from runwatch.prompts import TerminalPrompter
from runwatch.setup_wizard import interactive_config, persistent_spec
from runwatch.targets import LinuxTargetResolver, TargetResolutionError, TargetSpec


def _non_interactive_config(args: argparse.Namespace) -> RunwatchConfig:
    if not args.target:
        raise UsageError("--non-interactive requires at least one --target")

    resolver = LinuxTargetResolver()
    targets: list[TargetSpec] = []

    for value in args.target:
        candidate = TargetSpec(
            name=value.removesuffix(".service").split("/")[-1],
            kind="auto",
            value=value,
        )
        try:
            resolved = resolver.resolve(candidate)
        except TargetResolutionError as exc:
            raise UsageError(str(exc)) from exc
        targets.append(persistent_spec(candidate, resolved))

    return validate_config(
        RunwatchConfig(
            serve=ServeConfig(
                interval_seconds=args.interval,
                max_workers=args.max_workers,
            ),
            metrics=MetricsConfig(
                enabled=not args.no_metrics,
                address=args.metrics_address,
                port=args.metrics_port,
            ),
            targets=tuple(targets),
        )
    )


def _should_install(args: argparse.Namespace, prompter: TerminalPrompter) -> bool:
    if args.install:
        return True
    if args.no_install or args.non_interactive:
        return False
    return prompter.confirm("Install and start runwatch.service?", False)


def handle_setup(args: argparse.Namespace) -> int:
    prompter = TerminalPrompter()

    if args.non_interactive:
        config = _non_interactive_config(args)
    else:
        if not sys.stdin.isatty():
            raise UsageError("setup needs a TTY; use --non-interactive with --target")
        config = interactive_config(prompter)

    output = Path(args.output)
    write_text_atomic(output, render_config(config), overwrite=args.force)
    print(f"wrote {output}")

    if not _should_install(args, prompter):
        return 0

    executable = args.executable or shutil.which("runwatch")
    if executable is None:
        raise UsageError("runwatch executable was not found in PATH")

    install_systemd_service(
        executable=executable,
        config_source=output,
        force_unit=args.force,
        force_config=args.force_config,
        enable=not args.no_start,
    )

    print("installed runwatch.service")
    return 0
