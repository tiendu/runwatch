from __future__ import annotations

import argparse

from runwatch.cli import parse_args
from runwatch.commands import COMMAND_HANDLERS


def run(args: argparse.Namespace) -> int:
    """Dispatch one parsed command to its application workflow."""

    try:
        handler = COMMAND_HANDLERS[args.command]
    except KeyError:
        raise RuntimeError(f"unsupported command: {args.command}") from None
    return handler(args)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
