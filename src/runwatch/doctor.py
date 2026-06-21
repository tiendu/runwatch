from __future__ import annotations

import errno
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import psutil

from runwatch.config import RunwatchConfig, load_config
from runwatch.targets import LinuxTargetResolver, TargetResolutionError

DoctorStatus = Literal["pass", "info", "warn", "fail"]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: DoctorStatus
    message: str


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]
    config_path: str | None
    metrics_address: str
    metrics_port: int

    @property
    def exit_code(self) -> int:
        if any(check.status == "fail" for check in self.checks):
            return 2
        if any(check.status == "warn" for check in self.checks):
            return 1
        return 0


def _run(command: list[str], timeout: float = 3.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _systemd_check(*, user: bool) -> DoctorCheck:
    name = "systemd user manager" if user else "systemd system manager"
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        return DoctorCheck(name, "warn", "systemctl is not installed")

    command = [systemctl]
    if user:
        command.append("--user")
    command.extend(["show", "--property=Version", "--value"])
    try:
        result = _run(command)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DoctorCheck(name, "warn", f"could not query manager: {type(exc).__name__}: {exc}")

    if result.returncode == 0:
        version = result.stdout.strip()
        suffix = f" (version {version})" if version else ""
        return DoctorCheck(name, "pass", f"manager is reachable{suffix}")

    error = (result.stderr or result.stdout).strip().replace("\n", " ")
    return DoctorCheck(name, "warn", error or f"systemctl exited {result.returncode}")


def _procfs_check() -> DoctorCheck:
    required = [Path("/proc/self/status"), Path("/proc/self/fd")]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return DoctorCheck("procfs", "fail", f"missing required paths: {', '.join(missing)}")
    try:
        Path("/proc/self/status").read_text(encoding="utf-8")
        list(Path("/proc/self/fd").iterdir())
    except OSError as exc:
        return DoctorCheck("procfs", "fail", f"cannot inspect current process: {exc}")
    return DoctorCheck("procfs", "pass", "process metadata and file descriptors are readable")


def _cross_process_check() -> DoctorCheck:
    pid = 1
    try:
        process = psutil.Process(pid)
        process.status()
        process.memory_info()
    except (psutil.AccessDenied, PermissionError) as exc:
        return DoctorCheck(
            "cross-process visibility",
            "warn",
            f"PID 1 resource details are restricted: {type(exc).__name__}",
        )
    except (psutil.Error, OSError) as exc:
        return DoctorCheck(
            "cross-process visibility",
            "warn",
            f"could not inspect PID 1: {type(exc).__name__}: {exc}",
        )

    try:
        list(Path(f"/proc/{pid}/fd").iterdir())
    except OSError as exc:
        return DoctorCheck(
            "cross-process visibility",
            "warn",
            f"PID 1 resources are visible but descriptors are restricted: {exc}",
        )
    return DoctorCheck("cross-process visibility", "pass", "PID 1 resources are readable")


def _internet_socket_check() -> DoctorCheck:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = int(listener.getsockname()[1])
        connections = psutil.Process().net_connections(kind="inet")
        if any(connection.laddr and connection.laddr.port == port for connection in connections):
            return DoctorCheck(
                "TCP/UDP socket visibility",
                "pass",
                "current-process Internet sockets are visible",
            )
        return DoctorCheck(
            "TCP/UDP socket visibility",
            "warn",
            "test listener was not returned by process socket inspection",
        )
    except (OSError, psutil.Error) as exc:
        return DoctorCheck(
            "TCP/UDP socket visibility",
            "warn",
            f"socket inspection failed: {type(exc).__name__}: {exc}",
        )
    finally:
        listener.close()


def _unix_socket_check() -> DoctorCheck:
    if not hasattr(socket, "AF_UNIX"):
        return DoctorCheck("Unix socket visibility", "warn", "AF_UNIX is unavailable")

    with tempfile.TemporaryDirectory(prefix="runwatch-doctor-") as directory:
        path = str(Path(directory) / "doctor.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(path)
            listener.listen(1)
            connections = psutil.Process().net_connections(kind="unix")
            if any(str(connection.laddr) == path for connection in connections):
                return DoctorCheck(
                    "Unix socket visibility",
                    "pass",
                    "current-process Unix sockets are visible",
                )
            return DoctorCheck(
                "Unix socket visibility",
                "warn",
                "test Unix socket was not returned by process socket inspection",
            )
        except (OSError, psutil.Error) as exc:
            return DoctorCheck(
                "Unix socket visibility",
                "warn",
                f"Unix socket inspection failed: {type(exc).__name__}: {exc}",
            )
        finally:
            listener.close()


def _ebpf_check() -> DoctorCheck:
    btf = Path("/sys/kernel/btf/vmlinux").exists()
    bpf_fs = Path("/sys/fs/bpf").exists()
    bpftool = shutil.which("bpftool") is not None
    detected = [
        name for name, present in (("BTF", btf), ("bpffs", bpf_fs), ("bpftool", bpftool)) if present
    ]
    missing = [
        name
        for name, present in (("BTF", btf), ("bpffs", bpf_fs), ("bpftool", bpftool))
        if not present
    ]
    if btf and bpf_fs:
        message = f"kernel prerequisites detected ({', '.join(detected)}); network byte collector is optional and not enabled"
        if missing:
            message += f"; missing {', '.join(missing)}"
        return DoctorCheck("eBPF network accounting", "info", message)
    return DoctorCheck(
        "eBPF network accounting",
        "info",
        f"optional prerequisites are incomplete; missing {', '.join(missing)}",
    )


def _metrics_url(address: str, port: int) -> str:
    host = "127.0.0.1" if address in {"0.0.0.0", "::", ""} else address
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}/metrics"


def _is_runwatch_endpoint(address: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(_metrics_url(address, port), timeout=1.5) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
        return "runwatch_check_up" in body or "runwatch_target_up" in body
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _metrics_port_check(address: str, port: int, enabled: bool) -> DoctorCheck:
    if not enabled:
        return DoctorCheck("metrics endpoint", "info", "disabled by configuration")
    if not 1 <= port <= 65535:
        return DoctorCheck("metrics endpoint", "fail", f"invalid port {port}")

    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.bind((address, port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            if _is_runwatch_endpoint(address, port):
                return DoctorCheck(
                    "metrics endpoint",
                    "pass",
                    f"{address}:{port} is already serving Runwatch metrics",
                )
            return DoctorCheck(
                "metrics endpoint",
                "warn",
                f"{address}:{port} is already in use by another process",
            )
        return DoctorCheck(
            "metrics endpoint",
            "fail",
            f"cannot bind {address}:{port}: {type(exc).__name__}: {exc}",
        )
    finally:
        probe.close()
    return DoctorCheck("metrics endpoint", "pass", f"{address}:{port} is available")


def _discover_config(explicit_path: str | None) -> Path | None:
    if explicit_path is not None:
        return Path(explicit_path)
    for candidate in (Path("runwatch.toml"), Path("/etc/runwatch/runwatch.toml")):
        if candidate.exists():
            return candidate
    return None


def _config_checks(path: Path | None) -> tuple[list[DoctorCheck], RunwatchConfig | None]:
    if path is None:
        return [
            DoctorCheck(
                "configuration",
                "info",
                "no persistent config found; check and watch commands do not require one",
            )
        ], None
    if not path.exists():
        return [DoctorCheck("configuration", "fail", f"config does not exist: {path}")], None

    try:
        config = load_config(path)
    except (OSError, ValueError) as exc:
        return [
            DoctorCheck(
                "configuration",
                "fail",
                f"invalid config {path}: {type(exc).__name__}: {exc}",
            )
        ], None

    checks = [
        DoctorCheck(
            "configuration",
            "pass",
            f"{path} is valid ({len(config.targets)} targets, {len(config.http)} HTTP checks)",
        )
    ]
    if config.targets:
        resolver = LinuxTargetResolver()
        failures: list[str] = []
        for target in config.targets:
            try:
                resolved = resolver.resolve(target)
                if not resolved.pids and resolved.active_state not in {"active", "activating"}:
                    failures.append(f"{target.name}: no live processes")
            except TargetResolutionError as exc:
                failures.append(f"{target.name}: {exc}")
        if failures:
            checks.append(
                DoctorCheck(
                    "configured targets",
                    "warn",
                    "; ".join(failures[:5])
                    + (f"; and {len(failures) - 5} more" if len(failures) > 5 else ""),
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "configured targets",
                    "pass",
                    f"all {len(config.targets)} targets resolve",
                )
            )
    else:
        checks.append(DoctorCheck("configured targets", "info", "no persistent targets configured"))
    return checks, config


def run_doctor(
    *,
    config_path: str | None = None,
    metrics_address: str | None = None,
    metrics_port: int | None = None,
) -> DoctorReport:
    path = _discover_config(config_path)
    config_checks, config = _config_checks(path)

    address = (
        metrics_address
        if metrics_address is not None
        else config.metrics.address
        if config is not None
        else "127.0.0.1"
    )
    port = (
        metrics_port
        if metrics_port is not None
        else config.metrics.port
        if config is not None
        else 9109
    )
    metrics_enabled = config.metrics.enabled if config is not None else True

    checks: list[DoctorCheck] = [
        DoctorCheck(
            "platform",
            "pass" if sys.platform.startswith("linux") else "fail",
            f"{sys.platform}; Runwatch requires Linux",
        ),
        DoctorCheck(
            "Python",
            "pass" if sys.version_info >= (3, 11) else "fail",
            sys.version.split()[0],
        ),
        _systemd_check(user=False),
        _systemd_check(user=True),
        _procfs_check(),
        DoctorCheck(
            "cgroup v2",
            "pass" if Path("/sys/fs/cgroup/cgroup.controllers").exists() else "info",
            "available"
            if Path("/sys/fs/cgroup/cgroup.controllers").exists()
            else "not detected; process-tree fallback will be used",
        ),
        _cross_process_check(),
        _internet_socket_check(),
        _unix_socket_check(),
        _ebpf_check(),
        *config_checks,
        _metrics_port_check(address, port, metrics_enabled),
    ]
    return DoctorReport(
        checks=tuple(checks),
        config_path=str(path) if path is not None else None,
        metrics_address=address,
        metrics_port=port,
    )


def render_doctor_report(report: DoctorReport) -> str:
    symbols = {"pass": "✓", "info": "i", "warn": "!", "fail": "✗"}
    lines = ["Runwatch doctor", ""]
    width = max((len(check.name) for check in report.checks), default=0) + 2
    for check in report.checks:
        lines.append(f"{symbols[check.status]} {check.name:<{width}}{check.message}")

    counts = {status: sum(check.status == status for check in report.checks) for status in symbols}
    lines.extend(
        [
            "",
            "Summary",
            f"  {counts['pass']} passed, {counts['info']} informational, "
            f"{counts['warn']} warning(s), {counts['fail']} failure(s)",
        ]
    )
    return "\n".join(lines)


def doctor_to_json(report: DoctorReport) -> str:
    payload = {
        "schema_version": "1",
        "config_path": report.config_path,
        "metrics_address": report.metrics_address,
        "metrics_port": report.metrics_port,
        "exit_code": report.exit_code,
        "checks": [asdict(check) for check in report.checks],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
