from __future__ import annotations

import json
from datetime import UTC, datetime

from runwatch.results import CheckResult

_FIELD_WIDTH = 18


def _field(label: str, value: object) -> str:
    return f"{label:<{_FIELD_WIDTH}}{value}"


def _human_bytes(value: float | int | None, *, per_second: bool = False) -> str:
    if value is None:
        return "n/a"
    amount = float(value)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit = units[0]
    for candidate in units:
        unit = candidate
        if abs(amount) < 1024.0 or candidate == units[-1]:
            break
        amount /= 1024.0
    suffix = "/s" if per_second else ""
    return f"{amount:.1f} {unit}{suffix}"


def _uptime(started_at: float | None, now: float) -> str:
    if started_at is None:
        return "unknown"
    seconds = max(int(now - started_at), 0)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _coverage_text(details: dict[str, object], field: str) -> str | None:
    coverage = details.get("coverage")
    if not isinstance(coverage, dict):
        return None
    total = coverage.get("total_processes")
    visible = coverage.get(f"{field}_visible")
    if not isinstance(total, int) or not isinstance(visible, int) or total <= 0:
        return None
    if visible >= total:
        return None
    return f"partial: {visible}/{total} processes"


def _value_with_coverage(details: dict[str, object], key: str, coverage_field: str) -> str:
    value = str(details.get(key, 0))
    coverage = _coverage_text(details, coverage_field)
    return f"{value} ({coverage})" if coverage else value


def _remote_peers(details: dict[str, object]) -> list[str]:
    connections = details.get("connections")
    peers: set[tuple[str, int | None]] = set()
    if isinstance(connections, list):
        for item in connections:
            if not isinstance(item, dict):
                continue
            address = item.get("remote_address")
            port = item.get("remote_port")
            if isinstance(address, str) and address:
                peers.add((address, port if isinstance(port, int) else None))
    return [f"{address}:{port}" if port is not None else address for address, port in sorted(peers)]


def _unix_summary(details: dict[str, object]) -> tuple[int, int, int, list[str]]:
    raw_items = details.get("unix_sockets")
    items = raw_items if isinstance(raw_items, list) else []

    paths: set[str] = set()
    calculated_named = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        item_paths: set[str] = set()
        for key in ("local_path", "remote_path"):
            path = item.get(key)
            if isinstance(path, str) and path:
                item_paths.add(path)
                paths.add(path)
        if item_paths:
            calculated_named += 1

    named = details.get("named_unix_sockets")
    unnamed = details.get("unnamed_unix_sockets")
    named_count = named if isinstance(named, int) else calculated_named
    unnamed_count = unnamed if isinstance(unnamed, int) else max(len(items) - named_count, 0)

    raw_paths = details.get("named_unix_paths")
    if isinstance(raw_paths, list):
        paths.update(path for path in raw_paths if isinstance(path, str) and path)
    return len(items), named_count, unnamed_count, sorted(paths)


def result_to_json(result: CheckResult) -> str:
    payload = {
        "schema_version": "1",
        "observed_at": datetime.fromtimestamp(result.observed_at, UTC).isoformat(),
        "check_type": result.check_type,
        "name": result.name,
        "status": result.status,
        "message": result.message,
        "duration_seconds": result.duration_seconds,
        "details": result.details,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def render_target_result(result: CheckResult, *, verbose: bool = False) -> str:
    details = result.details
    if result.status == "fail" and "process_count" not in details:
        return "\n".join(
            [
                _field("Target", result.name),
                _field("Health", "FAIL"),
                _field("Error", result.message),
            ]
        )

    manager = str(details.get("manager") or "none")
    unit = details.get("unit")
    unit_type = str(details.get("unit_type") or "unit") if unit else None
    active_state = details.get("active_state")
    sub_state = details.get("sub_state")
    visibility = str(details.get("visibility") or "unknown")
    visibility_message = str(details.get("visibility_message") or "unknown")
    raw_rates = details.get("rates")
    rates: dict[str, object] = raw_rates if isinstance(raw_rates, dict) else {}
    listening = details.get("listening") if isinstance(details.get("listening"), list) else []
    states = (
        details.get("connection_states")
        if isinstance(details.get("connection_states"), dict)
        else {}
    )
    observed_at = result.observed_at
    cpu_value = rates.get("cpu_usage_cores")
    read_rate = rates.get("io_read_bytes_per_second")
    write_rate = rates.get("io_write_bytes_per_second")
    cpu_cores = float(cpu_value) if isinstance(cpu_value, (int, float)) else None
    read_bytes = float(read_rate) if isinstance(read_rate, (int, float)) else None
    write_bytes = float(write_rate) if isinstance(write_rate, (int, float)) else None

    lines = [
        _field("Target", result.name),
        _field("Health", f"{result.status.upper()} — {result.message}"),
        _field("Visibility", f"{visibility} — {visibility_message}"),
        _field("Manager", manager),
    ]
    if unit:
        lines.append(_field("Unit", unit))
        lines.append(_field("Unit type", unit_type))
        lines.append(_field("Unit state", f"{active_state}/{sub_state}"))
        if details.get("unit_file_state") is not None:
            lines.append(_field("Unit file", details.get("unit_file_state")))
        if unit_type == "service" and details.get("restart_count") is not None:
            lines.append(_field("Restarts", details.get("restart_count")))

    pid_label = "Leader PID" if unit_type == "scope" else "Main PID" if unit else "Root PID"
    started_at = details.get("started_at")
    lines.extend(
        [
            _field(pid_label, details.get("main_pid") or "n/a"),
            _field("Processes", details.get("process_count", 0)),
            _field("Threads", details.get("thread_count", 0)),
            _field("User", details.get("user") or "unknown"),
            _field(
                "Uptime",
                _uptime(started_at if isinstance(started_at, (int, float)) else None, observed_at),
            ),
            _field("Command", details.get("command") or "unknown"),
            "",
            _field("CPU", f"{cpu_cores * 100:.1f}%" if cpu_cores is not None else "sampling…"),
            _field(
                "Memory",
                _human_bytes(
                    details.get("memory_bytes")
                    if isinstance(details.get("memory_bytes"), (int, float))
                    else None
                ),
            ),
            _field("Disk read", _human_bytes(read_bytes, per_second=True)),
            _field("Disk write", _human_bytes(write_bytes, per_second=True)),
            _field(
                "File descriptors",
                _value_with_coverage(details, "file_descriptors", "file_descriptors"),
            ),
            _field(
                "Regular files",
                _value_with_coverage(details, "open_regular_files", "open_regular_files"),
            ),
            _field("Network I/O", "unavailable without eBPF"),
            "",
            "TCP/UDP listeners",
        ]
    )

    if listening:
        for item in listening:
            if not isinstance(item, dict):
                continue
            address = item.get("local_address") or "*"
            port = item.get("local_port")
            lines.append(f"  {str(item.get('protocol', '')).upper():4} {address}:{port}")
    else:
        lines.append("  none visible")
    internet_coverage = _coverage_text(details, "internet_sockets")
    if internet_coverage:
        lines.append(f"  ({internet_coverage})")

    peers = _remote_peers(details)
    lines.append("")
    lines.append("TCP/UDP connections")
    if states:
        for state, count in sorted(states.items()):
            lines.append(f"  {str(state).lower():16} {count}")
        lines.append(f"  {'unique peers':16} {len(peers)}")
    else:
        lines.append("  none visible")
    if internet_coverage:
        lines.append(f"  ({internet_coverage})")

    if peers:
        lines.append("")
        lines.append("Remote peers")
        lines.extend(f"  {peer}" for peer in peers[:10])
        if len(peers) > 10:
            lines.append(f"  … and {len(peers) - 10} more")

    unix_count, named_count, unnamed_count, unix_paths = _unix_summary(details)
    lines.append("")
    lines.append("IPC")
    unix_coverage = _coverage_text(details, "unix_sockets")
    unix_value = f"{unix_count} ({named_count} named, {unnamed_count} unnamed)"
    if unix_coverage:
        unix_value = f"{unix_value}; {unix_coverage}"
    lines.append(f"  {'Unix sockets':16} {unix_value}")
    if unix_paths:
        lines.append("  Named paths")
        lines.extend(f"    {path}" for path in unix_paths[:8])
        if len(unix_paths) > 8:
            lines.append(f"    … and {len(unix_paths) - 8} more")
    elif unix_count:
        lines.append("  Named paths      none visible")

    errors = details.get("errors")
    if verbose and isinstance(errors, list) and errors:
        lines.append("")
        lines.append("Collection details")
        lines.extend(f"  {error}" for error in errors[:20])
        if len(errors) > 20:
            lines.append(f"  … and {len(errors) - 20} more")
    elif isinstance(errors, list) and errors:
        lines.append("")
        lines.append(f"Collection notes  {len(errors)} hidden; rerun with --verbose")
    return "\n".join(lines)
