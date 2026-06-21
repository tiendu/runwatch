from __future__ import annotations

import argparse

from runwatch.config import load_config
from runwatch.service import serve


def handle_serve(args: argparse.Namespace) -> int:
    return serve(load_config(args.config))
