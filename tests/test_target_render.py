from runwatch.results import CheckResult
from runwatch.targets import render_target_result


def _partial_result() -> CheckResult:
    return CheckResult(
        check_type="target",
        name="ibus-daemon",
        status="ok",
        message="process tree is running with 2 process(es)",
        duration_seconds=0.1,
        details={
            "manager": "none",
            "process_count": 2,
            "thread_count": 4,
            "memory_bytes": 1024,
            "file_descriptors": 12,
            "open_regular_files": 0,
            "rates": {},
            "listening": [],
            "connections": [],
            "unix_sockets": [
                {
                    "socket_type": "stream",
                    "local_path": "/run/user/1000/bus",
                    "remote_path": None,
                    "status": "NONE",
                    "pid": 10,
                }
            ],
            "connection_states": {},
            "visibility": "partial",
            "visibility_message": "regular files 1/2; TCP/UDP sockets 1/2",
            "coverage": {
                "total_processes": 2,
                "cpu_visible": 2,
                "memory_visible": 2,
                "io_visible": 2,
                "threads_visible": 2,
                "file_descriptors_visible": 2,
                "open_regular_files_visible": 1,
                "internet_sockets_visible": 1,
                "unix_sockets_visible": 2,
            },
            "errors": ["PID 11 regular files: AccessDenied"],
        },
    )


def test_default_render_distinguishes_files_descriptors_and_ipc() -> None:
    output = render_target_result(_partial_result())

    assert "Health            OK" in output
    assert "Visibility        partial" in output
    assert "File descriptors  12" in output
    assert "Regular files     0 (partial: 1/2 processes)" in output
    assert "TCP/UDP listeners" in output
    assert "IPC" in output
    assert "Unix sockets     1 (1 named, 0 unnamed)" in output
    assert "/run/user/1000/bus" in output
    assert "PID 11" not in output
    assert "rerun with --verbose" in output


def test_verbose_render_shows_permission_errors() -> None:
    output = render_target_result(_partial_result(), verbose=True)

    assert "Collection details" in output
    assert "PID 11 regular files: AccessDenied" in output


def test_scope_render_uses_unit_aware_labels_and_peer_counts() -> None:
    result = CheckResult(
        check_type="target",
        name="firefox",
        status="ok",
        message="systemd user scope is active with 2 processes",
        duration_seconds=0.1,
        details={
            "manager": "systemd-user",
            "unit": "app-firefox.scope",
            "unit_type": "scope",
            "active_state": "active",
            "sub_state": "running",
            "unit_file_state": "transient",
            "restart_count": 0,
            "main_pid": 42,
            "process_count": 2,
            "thread_count": 3,
            "memory_bytes": 1024,
            "file_descriptors": 8,
            "open_regular_files": 2,
            "rates": {"cpu_usage_cores": 0.1},
            "listening": [],
            "connections": [
                {"remote_address": "1.2.3.4", "remote_port": 443},
                {"remote_address": "1.2.3.4", "remote_port": 443},
            ],
            "connection_states": {"ESTABLISHED": 2},
            "unix_sockets": [
                {"local_path": "/run/firefox.sock", "remote_path": None},
                {"local_path": None, "remote_path": None},
            ],
            "named_unix_sockets": 1,
            "unnamed_unix_sockets": 1,
            "named_unix_paths": ["/run/firefox.sock"],
            "visibility": "complete",
            "visibility_message": "all requested fields collected",
            "errors": [],
        },
    )

    output = render_target_result(result)

    assert "Unit type         scope" in output
    assert "Unit state        active/running" in output
    assert "Leader PID        42" in output
    assert "Restarts" not in output
    assert "unique peers     1" in output
    assert "Unix sockets     2 (1 named, 1 unnamed)" in output
    assert "Named paths" in output
