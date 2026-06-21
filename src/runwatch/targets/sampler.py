from __future__ import annotations

import socket
import stat
from pathlib import Path
from time import time

import psutil

from runwatch.targets.models import (
    CollectionCoverage,
    ResolvedTarget,
    SocketInfo,
    TargetSnapshot,
    UnixSocketInfo,
)


def _read_number(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _cgroup_path(target: ResolvedTarget) -> Path | None:
    if not target.cgroup:
        return None
    root = Path("/sys/fs/cgroup").resolve()
    path = (root / target.cgroup.lstrip("/")).resolve()
    if path != root and root not in path.parents:
        return None
    return path if path.exists() else None


def _cgroup_cpu_seconds(path: Path) -> float | None:
    try:
        values = dict(
            line.split(maxsplit=1)
            for line in (path / "cpu.stat").read_text(encoding="utf-8").splitlines()
            if " " in line
        )
        return int(values["usage_usec"]) / 1_000_000.0
    except (OSError, KeyError, ValueError):
        return None


def _cgroup_io_bytes(path: Path) -> tuple[int, int] | None:
    try:
        read_bytes = 0
        write_bytes = 0
        for line in (path / "io.stat").read_text(encoding="utf-8").splitlines():
            for item in line.split()[1:]:
                key, separator, value = item.partition("=")
                if not separator:
                    continue
                if key == "rbytes":
                    read_bytes += int(value)
                elif key == "wbytes":
                    write_bytes += int(value)
        return read_bytes, write_bytes
    except (OSError, ValueError):
        return None


def _address(value: object) -> tuple[str, int | None]:
    if not value:
        return "", None
    if hasattr(value, "ip") and hasattr(value, "port"):
        ip = getattr(value, "ip")
        port = getattr(value, "port")
        return str(ip), int(port)
    if isinstance(value, tuple):
        if len(value) >= 2:
            return str(value[0]), int(value[1])
        if len(value) == 1:
            return str(value[0]), None
    return str(value), None


def _unix_address(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _protocol(connection_type: int) -> str:
    if connection_type == socket.SOCK_DGRAM:
        return "udp"
    return "tcp"


def _unix_socket_type(connection_type: int) -> str:
    if connection_type == socket.SOCK_STREAM:
        return "stream"
    if connection_type == socket.SOCK_DGRAM:
        return "datagram"
    if connection_type == getattr(socket, "SOCK_SEQPACKET", -1):
        return "seqpacket"
    return "unknown"


def _process_file_descriptors(
    pid: int,
) -> tuple[int, int, str | None, str | None]:
    fd_path = Path(f"/proc/{pid}/fd")
    try:
        entries = list(fd_path.iterdir())
    except OSError as exc:
        message = f"{exc.__class__.__name__}: {exc}"
        return 0, 0, message, message

    regular_files = 0
    regular_error: str | None = None
    for entry in entries:
        try:
            mode = entry.stat().st_mode
        except FileNotFoundError:
            # File descriptors can disappear between listing and inspection.
            continue
        except OSError as exc:
            if regular_error is None:
                regular_error = f"{exc.__class__.__name__}: {exc}"
            continue
        if stat.S_ISREG(mode):
            regular_files += 1
    return len(entries), regular_files, None, regular_error


def _process_io_bytes(pid: int) -> tuple[int, int, str | None]:
    try:
        values: dict[str, int] = {}
        for line in Path(f"/proc/{pid}/io").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator:
                values[key.strip()] = int(value.strip())
        return values.get("read_bytes", 0), values.get("write_bytes", 0), None
    except (OSError, ValueError) as exc:
        return 0, 0, f"PID {pid} disk I/O: {exc.__class__.__name__}: {exc}"


def _process_internet_sockets(process: psutil.Process) -> tuple[list[SocketInfo], str | None]:
    sockets: list[SocketInfo] = []
    try:
        connections = process.net_connections(kind="inet")
    except (psutil.Error, OSError, IndexError, ValueError) as exc:
        return sockets, f"PID {process.pid} TCP/UDP sockets: {exc.__class__.__name__}: {exc}"
    for connection in connections:
        local_address, local_port = _address(connection.laddr)
        remote_address, remote_port = _address(connection.raddr)
        sockets.append(
            SocketInfo(
                protocol=_protocol(connection.type),
                local_address=local_address,
                local_port=local_port,
                remote_address=remote_address or None,
                remote_port=remote_port,
                state=connection.status or "NONE",
                pid=process.pid,
            )
        )
    return sockets, None


def _process_unix_sockets(
    process: psutil.Process,
) -> tuple[list[UnixSocketInfo], str | None]:
    sockets: list[UnixSocketInfo] = []
    try:
        connections = process.net_connections(kind="unix")
    except (psutil.Error, OSError, IndexError, ValueError) as exc:
        return sockets, f"PID {process.pid} Unix sockets: {exc.__class__.__name__}: {exc}"
    for connection in connections:
        sockets.append(
            UnixSocketInfo(
                socket_type=_unix_socket_type(connection.type),
                local_path=_unix_address(connection.laddr),
                remote_path=_unix_address(connection.raddr),
                status=connection.status or "NONE",
                pid=process.pid,
            )
        )
    return sockets, None


class LinuxTargetSampler:
    def sample(self, target: ResolvedTarget) -> TargetSnapshot:
        errors: list[str] = []
        cpu_time_seconds = 0.0
        memory_bytes = 0
        io_read_bytes = 0
        io_write_bytes = 0
        thread_count = 0
        file_descriptors = 0
        open_regular_files = 0
        internet_sockets: list[SocketInfo] = []
        unix_sockets: list[UnixSocketInfo] = []
        live_pids: list[int] = []

        cpu_visible = 0
        memory_visible = 0
        io_visible = 0
        threads_visible = 0
        file_descriptors_visible = 0
        open_regular_files_visible = 0
        internet_sockets_visible = 0
        unix_sockets_visible = 0

        cgroup = _cgroup_path(target)
        cgroup_cpu = _cgroup_cpu_seconds(cgroup) if cgroup else None
        cgroup_memory = _read_number(cgroup / "memory.current") if cgroup else None
        cgroup_io = _cgroup_io_bytes(cgroup) if cgroup else None

        def note(message: str) -> None:
            if message not in errors and len(errors) < 50:
                errors.append(message)

        for pid in target.pids:
            try:
                process = psutil.Process(pid)
                if not process.is_running():
                    continue
                live_pids.append(pid)
            except (psutil.Error, OSError, ValueError) as exc:
                note(f"PID {pid}: {exc.__class__.__name__}: {exc}")
                continue

            if cgroup_cpu is None:
                try:
                    cpu_times = process.cpu_times()
                    cpu_time_seconds += cpu_times.user + cpu_times.system
                    cpu_visible += 1
                except (psutil.Error, OSError, ValueError) as exc:
                    note(f"PID {pid} CPU: {exc.__class__.__name__}: {exc}")

            if cgroup_memory is None:
                try:
                    memory_bytes += process.memory_info().rss
                    memory_visible += 1
                except (psutil.Error, OSError, ValueError) as exc:
                    note(f"PID {pid} memory: {exc.__class__.__name__}: {exc}")

            if cgroup_io is None:
                read_bytes, write_bytes, io_error = _process_io_bytes(pid)
                if io_error is None:
                    io_read_bytes += read_bytes
                    io_write_bytes += write_bytes
                    io_visible += 1
                else:
                    note(io_error)

            try:
                thread_count += process.num_threads()
                threads_visible += 1
            except (psutil.Error, OSError, ValueError) as exc:
                note(f"PID {pid} threads: {exc.__class__.__name__}: {exc}")

            fd_count, regular_count, fd_error, regular_error = _process_file_descriptors(pid)
            file_descriptors += fd_count
            open_regular_files += regular_count
            if fd_error is None:
                file_descriptors_visible += 1
            else:
                note(f"PID {pid} file descriptors: {fd_error}")
            if regular_error is None and fd_error is None:
                open_regular_files_visible += 1
            else:
                note(f"PID {pid} regular files: {regular_error or fd_error}")

            process_internet_sockets, internet_error = _process_internet_sockets(process)
            if internet_error is None:
                internet_sockets.extend(process_internet_sockets)
                internet_sockets_visible += 1
            else:
                note(internet_error)

            process_unix_sockets, unix_error = _process_unix_sockets(process)
            if unix_error is None:
                unix_sockets.extend(process_unix_sockets)
                unix_sockets_visible += 1
            else:
                note(unix_error)

        total = len(live_pids)
        if cgroup_cpu is not None:
            cpu_time_seconds = cgroup_cpu
            cpu_visible = total
        if cgroup_memory is not None:
            memory_bytes = cgroup_memory
            memory_visible = total
        if cgroup_io is not None:
            io_read_bytes, io_write_bytes = cgroup_io
            io_visible = total

        deduplicated_internet = {
            (
                item.protocol,
                item.local_address,
                item.local_port,
                item.remote_address,
                item.remote_port,
                item.state,
                item.pid,
            ): item
            for item in internet_sockets
        }
        deduplicated_unix = {
            (
                item.socket_type,
                item.local_path,
                item.remote_path,
                item.status,
                item.pid,
            ): item
            for item in unix_sockets
        }

        return TargetSnapshot(
            observed_at=time(),
            target=target,
            process_count=total,
            thread_count=thread_count,
            cpu_time_seconds=cpu_time_seconds,
            memory_bytes=memory_bytes,
            io_read_bytes=io_read_bytes,
            io_write_bytes=io_write_bytes,
            file_descriptors=file_descriptors,
            open_regular_files=open_regular_files,
            internet_sockets=tuple(deduplicated_internet.values()),
            unix_sockets=tuple(deduplicated_unix.values()),
            coverage=CollectionCoverage(
                total_processes=total,
                cpu_visible=cpu_visible,
                memory_visible=memory_visible,
                io_visible=io_visible,
                threads_visible=threads_visible,
                file_descriptors_visible=file_descriptors_visible,
                open_regular_files_visible=open_regular_files_visible,
                internet_sockets_visible=internet_sockets_visible,
                unix_sockets_visible=unix_sockets_visible,
            ),
            errors=tuple(errors),
        )
