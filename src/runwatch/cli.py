from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from runwatch.config import DEFAULT_CONFIG, load_config, render_config
from runwatch.doctor import doctor_to_json, render_doctor_report, run_doctor
from runwatch.exporters import OpenMetricsExporter
from runwatch.installation import install_systemd_service
from runwatch.interfaces import ResultSink
from runwatch.logs import JsonResultLogger, emit_json_event, setup_logging
from runwatch.main import run_serve, sample_target_once, watch_target
from runwatch.prompts import TerminalPrompter
from runwatch.results import CheckResult
from runwatch.setup_wizard import interactive_config
from runwatch.targets import (
    LinuxTargetResolver,
    TargetResolutionError,
    TargetSpec,
    render_target_result,
    result_to_json,
)
from runwatch.templates import (
    DemoComposeTemplate,
    PrometheusAlertsTemplate,
    PrometheusScrapeTemplate,
    SystemdUnitTemplate,
)

DEFAULT_CONFIG_PATH = "/etc/runwatch/runwatch.toml"
DEFAULT_UNIT_PATH = "/etc/systemd/system/runwatch.service"


def _write(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise SystemExit(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    print(f"wrote {path}")


def _target_spec(args: argparse.Namespace) -> TargetSpec:
    selectors = [
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
        kind=kind,  # type: ignore[arg-type]
        value=text,
        include_children=not args.no_children,
    )


def cmd_init(args: argparse.Namespace) -> int:
    _write(Path(args.output), DEFAULT_CONFIG, args.force)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    if args.sample_seconds < 0:
        raise SystemExit("--sample-seconds must be zero or greater")
    spec = _target_spec(args)
    result = sample_target_once(spec, args.sample_seconds)
    print(
        result_to_json(result) if args.json else render_target_result(result, verbose=args.verbose)
    )
    return {"ok": 0, "warn": 1, "fail": 2}[result.status]


def cmd_watch(args: argparse.Namespace) -> int:
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")
    spec = _target_spec(args)
    clear = not args.no_clear and not args.json and sys.stdout.isatty()

    def output(result: CheckResult) -> None:
        if clear:
            print("\033[2J\033[H", end="")
        if args.json:
            print(result_to_json(result))
        else:
            print(render_target_result(result, verbose=args.verbose))

    try:
        return watch_target(spec, args.interval, output)
    except KeyboardInterrupt:
        return 0


def cmd_serve(args: argparse.Namespace) -> int:
    setup_logging()
    logger = logging.getLogger("runwatch")
    result_logger = JsonResultLogger(logger)
    config = load_config(args.config)
    sinks: list[ResultSink] = [result_logger]
    exporter: OpenMetricsExporter | None = None

    if config.metrics.enabled:
        exporter = OpenMetricsExporter(config.metrics)
        exporter.start()
        sinks.append(exporter)

    emit_json_event(
        logger,
        level="info",
        event="serve_started",
        message="runwatch persistent monitor started",
        target_count=len(config.targets),
        http_check_count=len(config.http),
        host_metrics_enabled=config.system.enabled,
        max_workers=config.serve.max_workers,
        interval_seconds=config.serve.interval_seconds,
        metrics_enabled=config.metrics.enabled,
        metrics_address=config.metrics.address if config.metrics.enabled else None,
        metrics_port=config.metrics.port if config.metrics.enabled else None,
    )

    try:
        run_serve(config, sinks)
    finally:
        if exporter is not None:
            exporter.stop()
        emit_json_event(
            logger,
            level="info",
            event="serve_stopped",
            message="runwatch persistent monitor stopped",
        )
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    if args.non_interactive:
        if not args.target:
            raise SystemExit("--non-interactive requires at least one --target")
        discovered_targets: list[TargetSpec] = []
        resolver = LinuxTargetResolver()
        for value in args.target:
            candidate = TargetSpec(
                name=value.removesuffix(".service").split("/")[-1],
                kind="auto",
                value=value,
            )
            try:
                resolved = resolver.resolve(candidate)
            except TargetResolutionError as exc:
                raise SystemExit(str(exc)) from exc
            if resolved.kind == "systemd" and resolved.manager == "systemd" and resolved.unit:
                candidate = TargetSpec(
                    name=candidate.name,
                    kind="systemd",
                    value=resolved.unit,
                )
            elif value.isdigit():
                candidate = TargetSpec(name=candidate.name, kind="pid", value=value)
            else:
                candidate = TargetSpec(name=candidate.name, kind="process", value=value)
            discovered_targets.append(candidate)
        targets = tuple(discovered_targets)
        from runwatch.config import MetricsConfig, RunwatchConfig, ServeConfig

        if args.interval <= 0 or args.max_workers <= 0:
            raise SystemExit("--interval and --max-workers must be greater than zero")
        if not 1 <= args.metrics_port <= 65535:
            raise SystemExit("--metrics-port must be between 1 and 65535")

        config = RunwatchConfig(
            serve=ServeConfig(
                interval_seconds=args.interval,
                max_workers=args.max_workers,
            ),
            metrics=MetricsConfig(
                enabled=not args.no_metrics,
                address=args.metrics_address,
                port=args.metrics_port,
            ),
            targets=targets,
        )
    else:
        if not sys.stdin.isatty():
            raise SystemExit("setup needs a TTY; use --non-interactive with --target")
        config = interactive_config(TerminalPrompter())

    output = Path(args.output)
    _write(output, render_config(config), args.force)

    install = args.install
    if not args.non_interactive and not args.no_install:
        install = TerminalPrompter().confirm("Install and start runwatch.service?", False)
    if install:
        executable = args.executable or shutil.which("runwatch")
        if executable is None:
            raise SystemExit("runwatch executable was not found in PATH")
        try:
            install_systemd_service(
                executable=executable,
                config_source=output,
                force_config=args.force_config,
                enable=not args.no_start,
            )
        except PermissionError as exc:
            raise SystemExit(f"{exc}; rerun setup with sudo or install later") from exc
        print("installed runwatch.service")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(
        f"valid: {len(config.targets)} target(s), {len(config.http)} HTTP check(s), "
        f"interval {config.serve.interval_seconds:g}s"
    )
    return 0


def cmd_gen_systemd(args: argparse.Namespace) -> int:
    executable = args.executable or shutil.which("runwatch") or "/usr/local/bin/runwatch"
    unit = SystemdUnitTemplate(
        config_path=args.config_path,
        executable=executable,
    ).render()
    if args.output:
        _write(Path(args.output), unit, args.force)
    else:
        print(unit)
    return 0


def cmd_install_systemd(args: argparse.Namespace) -> int:
    executable = args.executable or shutil.which("runwatch") or "/usr/local/bin/runwatch"
    source = Path(args.config_source)
    if not source.exists():
        raise SystemExit(f"config source does not exist: {source}")
    try:
        install_systemd_service(
            executable=executable,
            config_source=source,
            config_path=Path(args.config_path),
            unit_path=Path(args.unit_path),
            enable=args.enable,
            force_unit=args.force,
            force_config=args.force_config,
            dry_run=args.dry_run,
        )
    except PermissionError as exc:
        raise SystemExit(str(exc)) from exc
    print("installed runwatch systemd service" if not args.dry_run else "")
    return 0


def cmd_gen_prometheus(args: argparse.Namespace) -> int:
    content = PrometheusScrapeTemplate(host=args.host, port=args.port).render()
    if args.output:
        _write(Path(args.output), content, args.force)
    else:
        print(content)
    return 0


def cmd_gen_alerts(args: argparse.Namespace) -> int:
    content = PrometheusAlertsTemplate().render()
    if args.output:
        _write(Path(args.output), content, args.force)
    else:
        print(content)
    return 0


def cmd_gen_compose(args: argparse.Namespace) -> int:
    content = DemoComposeTemplate().render()
    if args.output:
        _write(Path(args.output), content, args.force)
    else:
        print(content)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(
        config_path=args.config,
        metrics_address=args.metrics_address,
        metrics_port=args.metrics_port,
    )
    print(doctor_to_json(report) if args.json else render_doctor_report(report))
    return report.exit_code


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

    p = sub.add_parser("check", help="inspect one service or process, then exit")
    _add_target_arguments(p)
    p.add_argument("--sample-seconds", type=float, default=1.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("watch", help="continuously watch one service or process in the terminal")
    _add_target_arguments(p)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("serve", help="continuously monitor configured targets and expose metrics")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("setup", help="guided persistent-monitoring setup")
    p.add_argument("--output", default="runwatch.toml")
    p.add_argument("--force", action="store_true")
    p.add_argument("--install", action="store_true")
    p.add_argument("--no-install", action="store_true")
    p.add_argument("--no-start", action="store_true")
    p.add_argument("--force-config", action="store_true")
    p.add_argument("--executable")
    p.add_argument("--non-interactive", action="store_true")
    p.add_argument("--target", action="append")
    p.add_argument("--interval", type=float, default=30.0)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--no-metrics", action="store_true")
    p.add_argument("--metrics-address", default="127.0.0.1")
    p.add_argument("--metrics-port", type=int, default=9109)
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("init", help="write a commented persistent-monitoring config")
    p.add_argument("--output", default="runwatch.toml")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="validate a TOML config")
    p.add_argument("--config", default="runwatch.toml")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("gen-systemd", help="print or write a systemd unit")
    p.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    p.add_argument("--executable")
    p.add_argument("--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_gen_systemd)

    p = sub.add_parser("install-systemd", help="install a config and systemd unit")
    p.add_argument("--config-source", default="runwatch.toml")
    p.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    p.add_argument("--unit-path", default=DEFAULT_UNIT_PATH)
    p.add_argument("--executable")
    p.add_argument("--enable", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--force-config", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_install_systemd)

    p = sub.add_parser("gen-prometheus", help="generate Prometheus scrape config")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=9109)
    p.add_argument("--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_gen_prometheus)

    p = sub.add_parser("gen-alerts", help="generate Prometheus alert rules")
    p.add_argument("--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_gen_alerts)

    p = sub.add_parser("gen-compose", help="generate an optional metrics-backend demo")
    p.add_argument("--output")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_gen_compose)

    p = sub.add_parser("doctor", help="check prerequisites, visibility, config, and metrics")
    p.add_argument("--config", help="config to validate; auto-detected when omitted")
    p.add_argument("--metrics-address", help="override the metrics address to probe")
    p.add_argument("--metrics-port", type=int, help="override the metrics port to probe")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
