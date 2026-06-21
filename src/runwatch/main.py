from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from runwatch.cli import parse_args
from runwatch.commands import COMMAND_HANDLERS
from runwatch.errors import RunwatchError


def run(args: argparse.Namespace) -> int:
    """Dispatch one parsed command to its application workflow."""

    try:
        handler = COMMAND_HANDLERS[args.command]
    except KeyError as exc:
        raise RuntimeError(f"unsupported command: {args.command}") from exc
    return handler(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and normalize expected failures into stable exit codes."""

    try:
        return run(parse_args(argv))
    except RunwatchError as exc:
        print(f"runwatch: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Match normal Unix CLI behavior when downstream closes the pipe.
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
