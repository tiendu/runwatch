from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TargetKind = Literal["auto", "systemd", "pid", "pid_file", "process"]
ResolvedKind = Literal["systemd", "process"]
VisibilityState = Literal["complete", "partial"]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    kind: TargetKind
    value: str
    include_children: bool = True


@dataclass(frozen=True)
class SocketInfo:
    protocol: str
    local_address: str
    local_port: int | None
    remote_address: str | None
    remote_port: int | None
    state: str
    pid: int

    @property
    def listening(self) -> bool:
        return self.state.upper() == "LISTEN" or (
            self.protocol == "udp" and self.remote_address is None
        )


@dataclass(frozen=True)
class UnixSocketInfo:
    socket_type: str
    local_path: str | None
    remote_path: str | None
    status: str
    pid: int

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(path for path in (self.local_path, self.remote_path) if path)


@dataclass(frozen=True)
class ResolvedTarget:
    name: str
    kind: ResolvedKind
    selector: str
    manager: str
    pids: tuple[int, ...]
    unit: str | None = None
    cgroup: str | None = None
    active_state: str | None = None
    sub_state: str | None = None
    main_pid: int | None = None
    command: str | None = None
    user: str | None = None
    started_at: float | None = None
    unit_file_state: str | None = None
    restart_count: int | None = None

    @property
    def unit_type(self) -> str | None:
        if self.unit is None:
            return None
        if self.unit.endswith(".scope"):
            return "scope"
        if self.unit.endswith(".service"):
            return "service"
        return "unit"


@dataclass(frozen=True)
class CollectionCoverage:
    total_processes: int
    cpu_visible: int
    memory_visible: int
    io_visible: int
    threads_visible: int
    file_descriptors_visible: int
    open_regular_files_visible: int
    internet_sockets_visible: int
    unix_sockets_visible: int

    def partial_fields(self) -> tuple[str, ...]:
        if self.total_processes <= 0:
            return ()
        fields = {
            "cpu": self.cpu_visible,
            "memory": self.memory_visible,
            "disk I/O": self.io_visible,
            "threads": self.threads_visible,
            "file descriptors": self.file_descriptors_visible,
            "regular files": self.open_regular_files_visible,
            "TCP/UDP sockets": self.internet_sockets_visible,
            "Unix sockets": self.unix_sockets_visible,
        }
        return tuple(
            f"{name} {visible}/{self.total_processes}"
            for name, visible in fields.items()
            if visible < self.total_processes
        )

    @property
    def complete(self) -> bool:
        return not self.partial_fields()


@dataclass(frozen=True)
class TargetSnapshot:
    observed_at: float
    target: ResolvedTarget
    process_count: int
    thread_count: int
    cpu_time_seconds: float
    memory_bytes: int
    io_read_bytes: int
    io_write_bytes: int
    file_descriptors: int
    open_regular_files: int
    internet_sockets: tuple[SocketInfo, ...] = ()
    unix_sockets: tuple[UnixSocketInfo, ...] = ()
    coverage: CollectionCoverage | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetRates:
    elapsed_seconds: float
    cpu_usage_cores: float | None
    io_read_bytes_per_second: float | None
    io_write_bytes_per_second: float | None


@dataclass(frozen=True)
class TargetReport:
    snapshot: TargetSnapshot
    rates: TargetRates
    status: Literal["ok", "warn", "fail"]
    message: str
    visibility: VisibilityState
    visibility_message: str
    connection_states: dict[str, int] = field(default_factory=dict)

    @property
    def listening_sockets(self) -> tuple[SocketInfo, ...]:
        return tuple(socket for socket in self.snapshot.internet_sockets if socket.listening)

    @property
    def remote_peers(self) -> tuple[tuple[str, int | None], ...]:
        peers = {
            (socket.remote_address, socket.remote_port)
            for socket in self.snapshot.internet_sockets
            if not socket.listening and socket.remote_address is not None
        }
        return tuple(sorted(peers, key=lambda item: (item[0], item[1] or 0)))

    @property
    def named_unix_socket_count(self) -> int:
        return sum(bool(socket.paths) for socket in self.snapshot.unix_sockets)

    @property
    def unnamed_unix_socket_count(self) -> int:
        return len(self.snapshot.unix_sockets) - self.named_unix_socket_count

    @property
    def named_unix_paths(self) -> tuple[str, ...]:
        return tuple(
            sorted({path for socket in self.snapshot.unix_sockets for path in socket.paths})
        )
