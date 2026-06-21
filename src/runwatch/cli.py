from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from runwatch.defaults import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_LOCAL_CONFIG_PATH,
    DEFAULT_MAX_WORKERS,
    DEFAULT_METRICS_ADDRESS,
    DEFAULT_METRICS_PORT,
    DEFAULT_SAMPLE_SECONDS,
    DEFAULT_SERVE_INTERVAL_SECONDS,
    DEFAULT_UNIT_PATH,
    DEFAULT_WATCH_INTERVAL_SECONDS,
)


def _package_version() -> str:
    try:
        return version("runwatch")
    except PackageNotFoundError:
        return "unknown"


def _non_negative_float(value: str) -> float:
    """Parse a finite floating-point CLI value that may be zero."""

    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from exc

    if parsed < 0 or parsed in {float("inf"), float("-inf")} or parsed != parsed:
        raise argparse.ArgumentTypeError("value must be finite and zero or greater")

    return parsed


def _positive_float(value: str) -> float:
    """Parse a strictly positive floating-point CLI value."""

    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a number, got {value!r}") from exc

    if parsed <= 0 or parsed in {float("inf"), float("-inf")} or parsed != parsed:
        raise argparse.ArgumentTypeError("value must be finite and greater than zero")

    return parsed


def _positive_int(value: str) -> int:
    """Parse a strictly positive integer CLI value."""

    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")

    return parsed


def _port(value: str) -> int:
    """Parse and validate a TCP port."""

    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer port, got {value!r}") from exc

    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")

    return parsed


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments that identify a service or process target."""

    parser.add_argument(
        "target",
        nargs="?",
        help="service name, process name, or PID",
    )
    parser.add_argument(
        "--service",
        metavar="UNIT",
        help="explicit systemd service or scope",
    )
    parser.add_argument(
        "--pid",
        type=_positive_int,
        metavar="PID",
        help="explicit PID; promotes to its specific systemd unit when appropriate",
    )
    parser.add_argument(
        "--pid-file",
        metavar="PATH",
        help="read the target PID from a file",
    )
    parser.add_argument(
        "--process",
        metavar="NAME_OR_PATH",
        help="exact process name or executable path",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        help="display and metric name",
    )
    parser.add_argument(
        "--no-children",
        action="store_true",
        help="do not include descendant processes",
    )


def _add_render_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_no_clear: bool = False,
) -> None:
    """Add common human-readable and machine-readable output options."""

    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show detailed collection and permission errors",
    )

    if include_no_clear:
        parser.add_argument(
            "--no-clear",
            action="store_true",
            help="do not clear the terminal between updates",
        )


def _add_output_arguments(
    parser: argparse.ArgumentParser,
    *,
    default: str | None = None,
) -> None:
    """Add common generated-file output options."""

    parser.add_argument(
        "--output",
        default=default,
        metavar="PATH",
        help="write output to this path instead of standard output",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing output file",
    )


def _add_metrics_arguments(
    parser: argparse.ArgumentParser,
    *,
    defaults: bool,
) -> None:
    """Add metrics endpoint arguments.

    Setup requires concrete defaults. Doctor uses ``None`` to distinguish
    omitted overrides from explicit values.
    """

    parser.add_argument(
        "--metrics-address",
        default=DEFAULT_METRICS_ADDRESS if defaults else None,
        metavar="ADDRESS",
        help="metrics endpoint listen or probe address",
    )
    parser.add_argument(
        "--metrics-port",
        type=_port,
        default=DEFAULT_METRICS_PORT if defaults else None,
        metavar="PORT",
        help="metrics endpoint listen or probe port",
    )


def _configure_check_parser(parser: argparse.ArgumentParser) -> None:
    _add_target_arguments(parser)
    _add_render_arguments(parser)
    parser.add_argument(
        "--sample-seconds",
        type=_non_negative_float,
        default=DEFAULT_SAMPLE_SECONDS,
        metavar="SECONDS",
        help="sampling window used to calculate CPU and I/O rates",
    )


def _configure_watch_parser(parser: argparse.ArgumentParser) -> None:
    _add_target_arguments(parser)
    _add_render_arguments(parser, include_no_clear=True)
    parser.add_argument(
        "--interval",
        type=_positive_float,
        default=DEFAULT_WATCH_INTERVAL_SECONDS,
        metavar="SECONDS",
        help="seconds between terminal updates",
    )


def _configure_serve_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        metavar="PATH",
        help="persistent-monitoring TOML config",
    )


def _configure_setup_parser(parser: argparse.ArgumentParser) -> None:
    _add_output_arguments(parser, default=str(DEFAULT_LOCAL_CONFIG_PATH))
    _add_metrics_arguments(parser, defaults=True)

    install_group = parser.add_mutually_exclusive_group()
    install_group.add_argument(
        "--install",
        action="store_true",
        help="install the generated config and systemd service",
    )
    install_group.add_argument(
        "--no-install",
        action="store_true",
        help="write the config without offering systemd installation",
    )

    parser.add_argument(
        "--no-start",
        action="store_true",
        help="install but do not start the systemd service",
    )
    parser.add_argument(
        "--force-config",
        action="store_true",
        help="replace an existing persistent config during installation",
    )
    parser.add_argument(
        "--executable",
        metavar="PATH",
        help="Runwatch executable used by the generated systemd unit",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="never prompt; require all necessary values from arguments",
    )
    parser.add_argument(
        "--target",
        action="append",
        metavar="TARGET",
        help="target to monitor; may be repeated",
    )
    parser.add_argument(
        "--interval",
        type=_positive_float,
        default=DEFAULT_SERVE_INTERVAL_SECONDS,
        metavar="SECONDS",
        help="seconds between persistent monitoring cycles",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=DEFAULT_MAX_WORKERS,
        metavar="COUNT",
        help="maximum number of concurrent checks",
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="disable the OpenMetrics endpoint",
    )


def _configure_init_parser(parser: argparse.ArgumentParser) -> None:
    _add_output_arguments(parser, default=str(DEFAULT_LOCAL_CONFIG_PATH))


def _configure_validate_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=str(DEFAULT_LOCAL_CONFIG_PATH),
        metavar="PATH",
        help="TOML config to validate",
    )


def _configure_gen_systemd_parser(parser: argparse.ArgumentParser) -> None:
    _add_output_arguments(parser)
    parser.add_argument(
        "--config-path",
        default=str(DEFAULT_CONFIG_PATH),
        metavar="PATH",
        help="config path embedded in the generated unit",
    )
    parser.add_argument(
        "--executable",
        metavar="PATH",
        help="Runwatch executable embedded in the generated unit",
    )


def _configure_install_systemd_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config-source",
        default=str(DEFAULT_LOCAL_CONFIG_PATH),
        metavar="PATH",
        help="source config to install",
    )
    parser.add_argument(
        "--config-path",
        default=str(DEFAULT_CONFIG_PATH),
        metavar="PATH",
        help="persistent config destination",
    )
    parser.add_argument(
        "--unit-path",
        default=str(DEFAULT_UNIT_PATH),
        metavar="PATH",
        help="systemd unit destination",
    )
    parser.add_argument(
        "--executable",
        metavar="PATH",
        help="Runwatch executable used by the installed unit",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="enable and start the installed service",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing systemd unit",
    )
    parser.add_argument(
        "--force-config",
        action="store_true",
        help="replace an existing persistent config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned changes without writing files or calling systemctl",
    )


def _configure_gen_prometheus_parser(parser: argparse.ArgumentParser) -> None:
    _add_output_arguments(parser)
    parser.add_argument(
        "--host",
        default="localhost",
        metavar="HOST",
        help="Runwatch host used in the generated scrape target",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=DEFAULT_METRICS_PORT,
        metavar="PORT",
        help="Runwatch metrics port used in the generated scrape target",
    )


def _configure_generated_output_parser(parser: argparse.ArgumentParser) -> None:
    _add_output_arguments(parser)


def _configure_doctor_parser(parser: argparse.ArgumentParser) -> None:
    _add_metrics_arguments(parser, defaults=False)
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="config to validate; auto-detected when omitted",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the complete Runwatch command-line parser."""

    parser = argparse.ArgumentParser(
        prog="runwatch",
        description="Inspect and monitor Linux services and processes.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        required=True,
    )

    check = subparsers.add_parser(
        "check",
        help="inspect one service or process, then exit",
        description="Inspect one service or process, then exit.",
    )
    _configure_check_parser(check)

    watch = subparsers.add_parser(
        "watch",
        help="continuously watch one service or process",
        description="Continuously watch one service or process in the terminal.",
    )
    _configure_watch_parser(watch)

    serve = subparsers.add_parser(
        "serve",
        help="run persistent configured monitoring",
        description="Continuously monitor configured targets and expose metrics.",
    )
    _configure_serve_parser(serve)

    setup = subparsers.add_parser(
        "setup",
        help="configure persistent monitoring",
        description=("Interactively or non-interactively configure persistent monitoring."),
    )
    _configure_setup_parser(setup)

    init = subparsers.add_parser(
        "init",
        help="write a commented config template",
        description="Write a commented persistent-monitoring config template.",
    )
    _configure_init_parser(init)

    validate = subparsers.add_parser(
        "validate",
        help="validate a TOML config",
        description="Validate a Runwatch TOML config.",
    )
    _configure_validate_parser(validate)

    gen_systemd = subparsers.add_parser(
        "gen-systemd",
        help="generate a systemd unit",
        description="Print or write a systemd unit for persistent Runwatch monitoring.",
    )
    _configure_gen_systemd_parser(gen_systemd)

    install_systemd = subparsers.add_parser(
        "install-systemd",
        help="install a config and systemd unit",
        description="Install a persistent config and systemd unit.",
    )
    _configure_install_systemd_parser(install_systemd)

    gen_prometheus = subparsers.add_parser(
        "gen-prometheus",
        help="generate a Prometheus scrape config",
        description="Generate a Prometheus-compatible scrape configuration.",
    )
    _configure_gen_prometheus_parser(gen_prometheus)

    gen_alerts = subparsers.add_parser(
        "gen-alerts",
        help="generate Prometheus alert rules",
        description="Generate Prometheus-compatible Runwatch alert rules.",
    )
    _configure_generated_output_parser(gen_alerts)

    gen_compose = subparsers.add_parser(
        "gen-compose",
        help="generate an optional metrics demo",
        description="Generate an optional metrics-backend Docker Compose demo.",
    )
    _configure_generated_output_parser(gen_compose)

    doctor = subparsers.add_parser(
        "doctor",
        help="check Runwatch prerequisites and visibility",
        description=("Check prerequisites, visibility, config, and metrics connectivity."),
    )
    _configure_doctor_parser(doctor)

    return parser


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    """Parse Runwatch command-line arguments."""

    return build_parser().parse_args(argv)
