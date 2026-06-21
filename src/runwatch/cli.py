from __future__ import annotations

import argparse

DEFAULT_CONFIG_PATH = "/etc/runwatch/runwatch.toml"
DEFAULT_UNIT_PATH = "/etc/systemd/system/runwatch.service"


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", nargs="?", help="service name, process name, or PID")
    parser.add_argument("--service", help="explicit systemd service")
    parser.add_argument("--pid", type=int, help="explicit PID; promotes to its systemd unit")
    parser.add_argument("--pid-file", help="read the PID from a file")
    parser.add_argument("--process", help="exact process name or executable path")
    parser.add_argument("--name", help="display/metric name")
    parser.add_argument("--no-children", action="store_true", help="do not include child processes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runwatch")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="inspect one service or process, then exit")
    _add_target_arguments(check)
    check.add_argument("--sample-seconds", type=float, default=1.0)
    check.add_argument("--json", action="store_true")
    check.add_argument("--verbose", action="store_true")

    watch = sub.add_parser(
        "watch",
        help="continuously watch one service or process in the terminal",
    )
    _add_target_arguments(watch)
    watch.add_argument("--interval", type=float, default=2.0)
    watch.add_argument("--json", action="store_true")
    watch.add_argument("--no-clear", action="store_true")
    watch.add_argument("--verbose", action="store_true")

    serve = sub.add_parser(
        "serve",
        help="continuously monitor configured targets and expose metrics",
    )
    serve.add_argument("--config", default=DEFAULT_CONFIG_PATH)

    setup = sub.add_parser("setup", help="guided persistent-monitoring setup")
    setup.add_argument("--output", default="runwatch.toml")
    setup.add_argument("--force", action="store_true")
    setup.add_argument("--install", action="store_true")
    setup.add_argument("--no-install", action="store_true")
    setup.add_argument("--no-start", action="store_true")
    setup.add_argument("--force-config", action="store_true")
    setup.add_argument("--executable")
    setup.add_argument("--non-interactive", action="store_true")
    setup.add_argument("--target", action="append")
    setup.add_argument("--interval", type=float, default=30.0)
    setup.add_argument("--max-workers", type=int, default=4)
    setup.add_argument("--no-metrics", action="store_true")
    setup.add_argument("--metrics-address", default="127.0.0.1")
    setup.add_argument("--metrics-port", type=int, default=9109)

    init = sub.add_parser("init", help="write a commented persistent-monitoring config")
    init.add_argument("--output", default="runwatch.toml")
    init.add_argument("--force", action="store_true")

    validate = sub.add_parser("validate", help="validate a TOML config")
    validate.add_argument("--config", default="runwatch.toml")

    gen_systemd = sub.add_parser("gen-systemd", help="print or write a systemd unit")
    gen_systemd.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    gen_systemd.add_argument("--executable")
    gen_systemd.add_argument("--output")
    gen_systemd.add_argument("--force", action="store_true")

    install_systemd = sub.add_parser("install-systemd", help="install a config and systemd unit")
    install_systemd.add_argument("--config-source", default="runwatch.toml")
    install_systemd.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    install_systemd.add_argument("--unit-path", default=DEFAULT_UNIT_PATH)
    install_systemd.add_argument("--executable")
    install_systemd.add_argument("--enable", action="store_true")
    install_systemd.add_argument("--force", action="store_true")
    install_systemd.add_argument("--force-config", action="store_true")
    install_systemd.add_argument("--dry-run", action="store_true")

    gen_prometheus = sub.add_parser(
        "gen-prometheus",
        help="generate Prometheus scrape config",
    )
    gen_prometheus.add_argument("--host", default="localhost")
    gen_prometheus.add_argument("--port", type=int, default=9109)
    gen_prometheus.add_argument("--output")
    gen_prometheus.add_argument("--force", action="store_true")

    gen_alerts = sub.add_parser("gen-alerts", help="generate Prometheus alert rules")
    gen_alerts.add_argument("--output")
    gen_alerts.add_argument("--force", action="store_true")

    gen_compose = sub.add_parser(
        "gen-compose",
        help="generate an optional metrics-backend demo",
    )
    gen_compose.add_argument("--output")
    gen_compose.add_argument("--force", action="store_true")

    doctor = sub.add_parser(
        "doctor",
        help="check prerequisites, visibility, config, and metrics",
    )
    doctor.add_argument("--config", help="config to validate; auto-detected when omitted")
    doctor.add_argument("--metrics-address", help="override the metrics address to probe")
    doctor.add_argument("--metrics-port", type=int, help="override the metrics port to probe")
    doctor.add_argument("--json", action="store_true")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)
