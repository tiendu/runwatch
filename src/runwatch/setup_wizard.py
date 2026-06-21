from __future__ import annotations

from dataclasses import replace

from runwatch.config import MetricsConfig, RunwatchConfig, ServeConfig, SystemConfig
from runwatch.prompts import Prompter
from runwatch.targets import LinuxTargetResolver, TargetResolutionError, TargetSpec


def _persistent_spec(input_spec: TargetSpec) -> TargetSpec:
    resolved = LinuxTargetResolver().resolve(input_spec)
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


def interactive_config(prompter: Prompter) -> RunwatchConfig:
    print("Runwatch persistent monitoring setup\n")
    targets: list[TargetSpec] = []

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
        kind = ("auto", "systemd", "pid", "pid_file", "process")[target_type]
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
        candidate = TargetSpec(name=name, kind=kind, value=value)  # type: ignore[arg-type]

        try:
            resolved = LinuxTargetResolver().resolve(candidate)
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
        targets.append(_persistent_spec(candidate))

        if not prompter.confirm("Add another target?", False):
            break

    interval = float(prompter.text("Collection interval in seconds", "30"))
    workers = int(prompter.text("Maximum concurrent checks", "4"))
    metrics_enabled = prompter.confirm("Expose an OpenMetrics endpoint?", True)
    address = "127.0.0.1"
    port = 9109
    if metrics_enabled:
        address = prompter.text("Metrics listen address", "127.0.0.1")
        port = int(prompter.text("Metrics port", "9109"))
    host_enabled = prompter.confirm("Also collect host CPU, memory, and disk usage?", True)

    return RunwatchConfig(
        serve=ServeConfig(interval_seconds=interval, max_workers=workers),
        metrics=MetricsConfig(enabled=metrics_enabled, address=address, port=port),
        system=SystemConfig(enabled=host_enabled),
        targets=tuple(targets),
    )
