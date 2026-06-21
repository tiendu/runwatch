from __future__ import annotations

import argparse
from pathlib import Path

from runwatch.config import DEFAULT_CONFIG, load_config
from runwatch.filesystem import write_text_atomic


def handle_init(args: argparse.Namespace) -> int:
    output = Path(args.output)
    write_text_atomic(output, DEFAULT_CONFIG, overwrite=args.force)
    print(f"wrote {output}")
    return 0


def handle_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(
        f"valid: {len(config.targets)} target(s), {len(config.http)} HTTP check(s), "
        f"interval {config.serve.interval_seconds:g}s"
    )
    return 0
