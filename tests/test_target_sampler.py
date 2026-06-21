import os
import socket
from pathlib import Path

from runwatch.targets import LinuxTargetSampler, ResolvedTarget


def test_sampler_collects_file_descriptors_and_unix_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "runwatch-test.sock"
    unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    unix_socket.bind(str(socket_path))
    unix_socket.listen(1)
    try:
        pid = os.getpid()
        snapshot = LinuxTargetSampler().sample(
            ResolvedTarget(
                name="self",
                kind="process",
                selector=str(pid),
                manager="none",
                main_pid=pid,
                pids=(pid,),
            )
        )
    finally:
        unix_socket.close()

    assert snapshot.file_descriptors > 0
    assert snapshot.open_regular_files >= 0
    assert any(str(socket_path) in item.paths for item in snapshot.unix_sockets)
    assert snapshot.coverage is not None
    assert snapshot.coverage.file_descriptors_visible == 1
    assert snapshot.coverage.unix_sockets_visible == 1
