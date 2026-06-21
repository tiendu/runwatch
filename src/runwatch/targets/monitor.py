from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from time import perf_counter

from runwatch.interfaces import TargetResolver, TargetSampler
from runwatch.results import CheckResult, MetricSample, Status
from runwatch.targets.models import (
    TargetRates,
    TargetReport,
    TargetSnapshot,
    TargetSpec,
    VisibilityState,
)
from runwatch.targets.resolver import TargetResolutionError


def compare_snapshots(
    previous: TargetSnapshot | None,
    current: TargetSnapshot,
) -> TargetRates:
    if previous is None:
        return TargetRates(
            elapsed_seconds=0.0,
            cpu_usage_cores=None,
            io_read_bytes_per_second=None,
            io_write_bytes_per_second=None,
        )

    elapsed = max(current.observed_at - previous.observed_at, 0.0)
    if elapsed <= 0:
        return TargetRates(elapsed, None, None, None)

    cpu_delta = current.cpu_time_seconds - previous.cpu_time_seconds
    read_delta = current.io_read_bytes - previous.io_read_bytes
    write_delta = current.io_write_bytes - previous.io_write_bytes
    return TargetRates(
        elapsed_seconds=elapsed,
        cpu_usage_cores=max(cpu_delta, 0.0) / elapsed,
        io_read_bytes_per_second=max(read_delta, 0) / elapsed,
        io_write_bytes_per_second=max(write_delta, 0) / elapsed,
    )


def _status(snapshot: TargetSnapshot) -> tuple[Status, str]:
    target = snapshot.target
    if target.kind == "systemd" and target.active_state == "failed":
        state = "/".join(filter(None, [target.active_state, target.sub_state]))
        return "fail", f"{target.unit} is {state}"
    if target.kind == "systemd" and target.active_state == "inactive":
        state = "/".join(filter(None, [target.active_state, target.sub_state]))
        return "fail", f"{target.unit} is {state}"
    if snapshot.process_count == 0:
        return "fail", "target has no live processes"

    process_word = "process" if snapshot.process_count == 1 else "processes"
    if target.manager == "systemd-user" and target.unit_type == "scope":
        manager = "systemd user scope"
    elif target.manager == "systemd-user":
        manager = "systemd user service"
    elif target.unit_type == "scope":
        manager = "systemd scope"
    elif target.unit:
        manager = "systemd service"
    else:
        manager = "process tree"
    return "ok", f"{manager} is active with {snapshot.process_count} {process_word}"


def _visibility(snapshot: TargetSnapshot) -> tuple[VisibilityState, str]:
    coverage = snapshot.coverage
    if coverage is None:
        if snapshot.errors:
            return "partial", f"{len(snapshot.errors)} collection error(s)"
        return "complete", "all requested fields collected"

    partial = coverage.partial_fields()
    if not partial and not snapshot.errors:
        return "complete", "all requested fields collected"
    if partial:
        return "partial", "; ".join(partial)
    return "partial", f"{len(snapshot.errors)} collection error(s)"


def _metrics(report: TargetReport) -> tuple[MetricSample, ...]:
    snapshot = report.snapshot
    target = snapshot.target
    labels = {"name": target.name}
    samples = [
        MetricSample(
            name="runwatch_target_up",
            help="Whether the monitored target is running.",
            value=1.0 if report.status in {"ok", "warn"} else 0.0,
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_visibility_complete",
            help="Whether all requested target fields were collected.",
            value=1.0 if report.visibility == "complete" else 0.0,
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_collection_errors",
            help="Number of collection errors from the latest target sample.",
            value=float(len(snapshot.errors)),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_processes",
            help="Number of live processes in the monitored target.",
            value=float(snapshot.process_count),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_threads",
            help="Number of visible threads in the monitored target.",
            value=float(snapshot.thread_count),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_memory_bytes",
            help="Current visible memory used by the monitored target in bytes.",
            value=float(snapshot.memory_bytes),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_io_read_bytes_total",
            help="Cumulative visible bytes read by the monitored target.",
            value=float(snapshot.io_read_bytes),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_io_write_bytes_total",
            help="Cumulative visible bytes written by the monitored target.",
            value=float(snapshot.io_write_bytes),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_file_descriptors",
            help="Number of visible file descriptors owned by the target.",
            value=float(snapshot.file_descriptors),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_open_regular_files",
            help="Number of open regular files visible to runwatch.",
            value=float(snapshot.open_regular_files),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_internet_listening_sockets",
            help="Number of visible listening TCP or UDP sockets owned by the target.",
            value=float(len(report.listening_sockets)),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_unix_sockets",
            help="Number of visible Unix-domain sockets owned by the target.",
            value=float(len(snapshot.unix_sockets)),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_unix_sockets_named",
            help="Number of visible Unix-domain sockets with a printable path.",
            value=float(report.named_unix_socket_count),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_unix_sockets_unnamed",
            help="Number of visible Unix-domain sockets without a printable path.",
            value=float(report.unnamed_unix_socket_count),
            labels=labels,
        ),
        MetricSample(
            name="runwatch_target_unique_remote_peers",
            help="Number of unique visible remote TCP or UDP peers.",
            value=float(len(report.remote_peers)),
            labels=labels,
        ),
    ]
    if target.restart_count is not None and target.unit_type == "service":
        samples.append(
            MetricSample(
                name="runwatch_target_restarts_total",
                help="Number of restarts reported by the target's service manager.",
                value=float(target.restart_count),
                labels=labels,
            )
        )

    if report.rates.cpu_usage_cores is not None:
        samples.extend(
            [
                MetricSample(
                    name="runwatch_target_cpu_usage_cores",
                    help="Visible CPU consumed by the target measured in logical CPU cores.",
                    value=report.rates.cpu_usage_cores,
                    labels=labels,
                ),
                MetricSample(
                    name="runwatch_target_io_read_bytes_per_second",
                    help="Visible target disk read throughput in bytes per second.",
                    value=report.rates.io_read_bytes_per_second or 0.0,
                    labels=labels,
                ),
                MetricSample(
                    name="runwatch_target_io_write_bytes_per_second",
                    help="Visible target disk write throughput in bytes per second.",
                    value=report.rates.io_write_bytes_per_second or 0.0,
                    labels=labels,
                ),
            ]
        )

    for state, count in sorted(report.connection_states.items()):
        samples.append(
            MetricSample(
                name="runwatch_target_connections",
                help="Number of visible target network connections grouped by state.",
                value=float(count),
                labels={"name": target.name, "state": state.lower()},
            )
        )
    return tuple(samples)


def _report_details(report: TargetReport) -> dict[str, object]:
    snapshot = report.snapshot
    target = snapshot.target
    return {
        "manager": target.manager,
        "kind": target.kind,
        "unit": target.unit,
        "unit_type": target.unit_type,
        "active_state": target.active_state,
        "sub_state": target.sub_state,
        "main_pid": target.main_pid,
        "pids": list(target.pids),
        "cgroup": target.cgroup,
        "command": target.command,
        "user": target.user,
        "started_at": target.started_at,
        "unit_file_state": target.unit_file_state,
        "restart_count": target.restart_count,
        "process_count": snapshot.process_count,
        "thread_count": snapshot.thread_count,
        "memory_bytes": snapshot.memory_bytes,
        "cpu_time_seconds": snapshot.cpu_time_seconds,
        "io_read_bytes": snapshot.io_read_bytes,
        "io_write_bytes": snapshot.io_write_bytes,
        "file_descriptors": snapshot.file_descriptors,
        "open_regular_files": snapshot.open_regular_files,
        "rates": asdict(report.rates),
        "listening": [asdict(socket) for socket in report.listening_sockets],
        "connections": [
            asdict(socket) for socket in snapshot.internet_sockets if not socket.listening
        ],
        "unix_sockets": [asdict(socket) for socket in snapshot.unix_sockets],
        "connection_states": report.connection_states,
        "unique_remote_peers": len(report.remote_peers),
        "named_unix_sockets": report.named_unix_socket_count,
        "unnamed_unix_sockets": report.unnamed_unix_socket_count,
        "named_unix_paths": list(report.named_unix_paths),
        "network_bytes": None,
        "network_bytes_note": (
            "per-target network byte accounting requires an optional eBPF collector"
        ),
        "visibility": report.visibility,
        "visibility_message": report.visibility_message,
        "coverage": asdict(snapshot.coverage) if snapshot.coverage is not None else None,
        "errors": list(snapshot.errors),
    }


class TargetMonitor:
    check_type = "target"

    def __init__(
        self,
        spec: TargetSpec,
        resolver: TargetResolver,
        sampler: TargetSampler,
    ) -> None:
        self.spec = spec
        self.name = spec.name
        self._resolver = resolver
        self._sampler = sampler
        self._previous: TargetSnapshot | None = None

    def run_report(self) -> TargetReport:
        target = self._resolver.resolve(self.spec)
        snapshot = self._sampler.sample(target)
        rates = compare_snapshots(self._previous, snapshot)
        self._previous = snapshot
        status, message = _status(snapshot)
        visibility, visibility_message = _visibility(snapshot)
        states = Counter(
            socket.state.upper() for socket in snapshot.internet_sockets if not socket.listening
        )
        return TargetReport(
            snapshot=snapshot,
            rates=rates,
            status=status,
            message=message,
            visibility=visibility,
            visibility_message=visibility_message,
            connection_states=dict(states),
        )

    def run(self) -> CheckResult:
        started = perf_counter()
        try:
            report = self.run_report()
            return CheckResult(
                check_type=self.check_type,
                name=self.name,
                status=report.status,
                message=report.message,
                duration_seconds=perf_counter() - started,
                labels={"manager": report.snapshot.target.manager},
                metrics=_metrics(report),
                details=_report_details(report),
            )
        except TargetResolutionError as exc:
            labels = {"name": self.name}
            return CheckResult(
                check_type=self.check_type,
                name=self.name,
                status="fail",
                message=str(exc),
                duration_seconds=perf_counter() - started,
                metrics=(
                    MetricSample(
                        name="runwatch_target_up",
                        help="Whether the monitored target is running.",
                        value=0.0,
                        labels=labels,
                    ),
                    MetricSample(
                        name="runwatch_target_processes",
                        help="Number of live processes in the monitored target.",
                        value=0.0,
                        labels=labels,
                    ),
                    MetricSample(
                        name="runwatch_target_internet_listening_sockets",
                        help="Number of visible listening TCP or UDP sockets owned by the target.",
                        value=0.0,
                        labels=labels,
                    ),
                    MetricSample(
                        name="runwatch_target_unix_sockets",
                        help="Number of visible Unix-domain sockets owned by the target.",
                        value=0.0,
                        labels=labels,
                    ),
                    MetricSample(
                        name="runwatch_target_unix_sockets_named",
                        help="Number of visible Unix-domain sockets with a printable path.",
                        value=0.0,
                        labels=labels,
                    ),
                    MetricSample(
                        name="runwatch_target_unix_sockets_unnamed",
                        help="Number of visible Unix-domain sockets without a printable path.",
                        value=0.0,
                        labels=labels,
                    ),
                    MetricSample(
                        name="runwatch_target_unique_remote_peers",
                        help="Number of unique visible remote TCP or UDP peers.",
                        value=0.0,
                        labels=labels,
                    ),
                ),
                details={"target_kind": self.spec.kind, "target_value": self.spec.value},
            )
