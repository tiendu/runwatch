from __future__ import annotations

import argparse
from collections.abc import Callable

from runwatch.commands.config import handle_init, handle_validate
from runwatch.commands.doctor import handle_doctor
from runwatch.commands.generate import (
    handle_gen_alerts,
    handle_gen_compose,
    handle_gen_prometheus,
    handle_gen_systemd,
)
from runwatch.commands.serve import handle_serve
from runwatch.commands.setup import handle_setup
from runwatch.commands.systemd import handle_install_systemd
from runwatch.commands.target import handle_check, handle_watch

CommandHandler = Callable[[argparse.Namespace], int]

COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "check": handle_check,
    "watch": handle_watch,
    "serve": handle_serve,
    "setup": handle_setup,
    "init": handle_init,
    "validate": handle_validate,
    "gen-systemd": handle_gen_systemd,
    "install-systemd": handle_install_systemd,
    "gen-prometheus": handle_gen_prometheus,
    "gen-alerts": handle_gen_alerts,
    "gen-compose": handle_gen_compose,
    "doctor": handle_doctor,
}

__all__ = ["COMMAND_HANDLERS", "CommandHandler"]
