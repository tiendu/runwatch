from __future__ import annotations

import argparse
import sys
from runwatch.execution import exit_code_for
from runwatch.results import CheckResult
from runwatch.target_runtime import sample_target_once, watch_target
from runwatch.targets import TargetSpec, render_target_result, result_to_json
from runwatch.targets.models import TargetKind


def target_spec_from_args(args: argparse.Namespace) -> TargetSpec:
    selectors: list[tuple[TargetKind, object | None]] = [
        ("auto", args.target),
        ("pid", args.pid),
        ("pid_file", args.pid_file),
        ("process", args.process),
        ("systemd", args.service),
    ]
    chosen = [(kind, value) for kind, value in selectors if value is not None]
    if len(chosen) != 1:
        raise SystemExit("provide exactly one TARGET, --service, --pid, --pid-file, or --process")

    kind, value = chosen[0]
    text = str(value)
    name = args.name or text.removesuffix(".service").split("/")[-1]
    return TargetSpec(
        name=name,
        kind=kind,
        value=text,
        include_children=not args.no_children,
    )


def handle_check(args: argparse.Namespace) -> int:
    if args.sample_seconds < 0:
        raise SystemExit("--sample-seconds must be zero or greater")

    result = sample_target_once(target_spec_from_args(args), args.sample_seconds)
    print(
        result_to_json(result) if args.json else render_target_result(result, verbose=args.verbose)
    )
    return exit_code_for(result)


def handle_watch(args: argparse.Namespace) -> int:
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")

    spec = target_spec_from_args(args)
    clear = not args.no_clear and not args.json and sys.stdout.isatty()

    def output(result: CheckResult) -> None:
        if clear:
            print("\033[2J\033[H", end="")
        print(
            result_to_json(result)
            if args.json
            else render_target_result(result, verbose=args.verbose)
        )

    try:
        return watch_target(spec, args.interval, output)
    except KeyboardInterrupt:
        return 0
