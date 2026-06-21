from __future__ import annotations

from dataclasses import replace

from runwatch.config import (
    MetricsConfig,
    RunwatchConfig,
    ServeConfig,
    SystemConfig,
    validate_config,
)
from runwatch.prompts import Prompter
from runwatch.targets import (
    LinuxTargetResolver,
    ResolvedTarget,
    TargetResolutionError,
    TargetSpec,
)
from runwatch.targets.models import TargetKind


def persistent_spec(
    input_spec: TargetSpec,
    resolved: ResolvedTarget | None = None,
) -> TargetSpec:
    resolved = resolved or LinuxTargetResolver().resolve(input_spec)
    if resolved.kind == "systemd" and resolved.manager == "systemd" and resolved.unit:
        return TargetSpec(
            name=input_spec.name,
            kind="systemd",
            value=resolved.unit,
            include_children=True,
        )
    # Preserve a process selector rather than a PID when possible so restarts can be followed.
    if input_spec.kind in {"process", "pid_file"}:
        return input_spec
    if input_spec.kind == "auto" and not input_spec.value.isdigit():
        return replace(input_spec, kind="process")
    return replace(input_spec, kind="pid", value=str(resolved.main_pid or input_spec.value))


def _prompt_positive_float(prompter: Prompter, message: str, default: str) -> float:
    while True:
        raw = prompter.text(message, default)
        try:
            value = float(raw)
        except ValueError:
            print("Enter a number.")
            continue
        if value > 0 and value != float("inf"):
            return value
        print("Enter a finite number greater than zero.")


def _prompt_positive_int(prompter: Prompter, message: str, default: str) -> int:
    while True:
        raw = prompter.text(message, default)
        try:
            value = int(raw)
        except ValueError:
            print("Enter an integer.")
            continue
        if value > 0:
            return value
        print("Enter an integer greater than zero.")


def _prompt_port(prompter: Prompter, message: str, default: str) -> int:
    while True:
        value = _prompt_positive_int(prompter, message, default)
        if value <= 65535:
            return value
        print("Enter a port between 1 and 65535.")


def interactive_config(prompter: Prompter) -> RunwatchConfig:
    print("Runwatch persistent monitoring setup\n")
    targets: list[TargetSpec] = []
    resolver = LinuxTargetResolver()

    while True:
        target_type = prompter.select(
            "What do you want to monitor?",
            [
                "Auto-detect a service or process",
                "A systemd service",
                "A PID",
                "A PID file",
                "A process name or executable",
            ],
        )
        kind: TargetKind = ("auto", "systemd", "pid", "pid_file", "process")[target_type]
        value = prompter.text(
            {
                "auto": "Service/process name",
                "systemd": "Systemd service",
                "pid": "PID",
                "pid_file": "PID file",
                "process": "Process name or executable",
            }[kind]
        )
        default_name = value.removesuffix(".service").split("/")[-1]
        name = prompter.text("Target name", default_name)
        candidate = TargetSpec(name=name, kind=kind, value=value)

        try:
            resolved = resolver.resolve(candidate)
        except TargetResolutionError as exc:
            print(f"✗ {exc}")
            if prompter.confirm("Try another target?", True):
                continue
            raise

        print(f"✓ Manager: {resolved.manager}")
        if resolved.unit:
            print(f"✓ Unit: {resolved.unit} ({resolved.active_state}/{resolved.sub_state})")
        print(f"✓ Processes: {len(resolved.pids)}")
        if resolved.main_pid:
            print(f"✓ Main PID: {resolved.main_pid}")
        targets.append(persistent_spec(candidate, resolved))

        if not prompter.confirm("Add another target?", False):
            break

    interval = _prompt_positive_float(prompter, "Collection interval in seconds", "30")
    workers = _prompt_positive_int(prompter, "Maximum concurrent checks", "4")
    metrics_enabled = prompter.confirm("Expose an OpenMetrics endpoint?", True)
    address = "127.0.0.1"
    port = 9109
    if metrics_enabled:
        address = prompter.text("Metrics listen address", "127.0.0.1")
        port = _prompt_port(prompter, "Metrics port", "9109")
    host_enabled = prompter.confirm("Also collect host CPU, memory, and disk usage?", True)

    return validate_config(
        RunwatchConfig(
            serve=ServeConfig(interval_seconds=interval, max_workers=workers),
            metrics=MetricsConfig(enabled=metrics_enabled, address=address, port=port),
            system=SystemConfig(enabled=host_enabled),
            targets=tuple(targets),
        )
    )
