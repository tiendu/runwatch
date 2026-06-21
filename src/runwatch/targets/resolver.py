from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psutil

from runwatch.targets.models import ResolvedTarget, TargetSpec


class TargetResolutionError(RuntimeError):
    pass


class AmbiguousTargetError(TargetResolutionError):
    pass


@dataclass(frozen=True)
class _SystemdMembership:
    unit: str
    manager: str
    cgroup: str


_USER_MANAGER = re.compile(r"^user@\d+\.service$")
_SESSION_SCOPE = re.compile(r"^session-[^.]+\.scope$")


def _run_systemctl_show(
    unit: str,
    timeout_seconds: float = 3.0,
    *,
    user_scope: bool = False,
) -> dict[str, str] | None:
    command = ["systemctl"]
    if user_scope:
        command.append("--user")
    command.extend(
        [
            "show",
            unit,
            "--no-pager",
            "--property=Id,LoadState,ActiveState,SubState,MainPID,Leader,ControlGroup,ExecMainStartTimestamp,NRestarts,UnitFileState",
        ]
    )
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    if not values or values.get("LoadState") == "not-found":
        return None
    return values


def _cgroup_from_pid(pid: int) -> str | None:
    try:
        content = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
    except OSError:
        return None

    fallback: str | None = None
    for line in content.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        _hierarchy, controllers, path = parts
        if not path.startswith("/"):
            continue
        if fallback is None:
            fallback = path
        controller_names = set(filter(None, controllers.split(",")))
        if not controller_names or "name=systemd" in controller_names:
            return path
    return fallback


def _membership_from_cgroup(cgroup: str) -> _SystemdMembership | None:
    components = [component for component in cgroup.split("/") if component]
    user_scope = "user.slice" in components

    chosen_index: int | None = None
    chosen_unit: str | None = None
    for index, component in enumerate(components):
        if component.endswith(".service"):
            if _USER_MANAGER.fullmatch(component):
                continue
            chosen_index = index
            chosen_unit = component
            continue
        if component.endswith(".scope"):
            if component == "init.scope" or _SESSION_SCOPE.fullmatch(component):
                continue
            chosen_index = index
            chosen_unit = component

    if chosen_index is None or chosen_unit is None:
        return None

    manager = "systemd-user" if user_scope else "systemd"
    unit_cgroup = "/" + "/".join(components[: chosen_index + 1])
    return _SystemdMembership(unit=chosen_unit, manager=manager, cgroup=unit_cgroup)


def _systemd_membership_from_pid(pid: int) -> _SystemdMembership | None:
    cgroup = _cgroup_from_pid(pid)
    return _membership_from_cgroup(cgroup) if cgroup else None


def _read_cgroup_pids(cgroup: str) -> tuple[int, ...]:
    relative = cgroup.lstrip("/")
    root = (Path("/sys/fs/cgroup") / relative).resolve()
    cgroup_root = Path("/sys/fs/cgroup").resolve()
    if cgroup_root not in root.parents and root != cgroup_root:
        return ()
    if not root.exists():
        return ()

    pids: set[int] = set()
    for path in [root, *root.glob("**/cgroup.procs")]:
        procs_file = path if path.name == "cgroup.procs" else path / "cgroup.procs"
        try:
            for value in procs_file.read_text(encoding="utf-8").split():
                pid = int(value)
                if psutil.pid_exists(pid):
                    pids.add(pid)
        except (OSError, ValueError):
            continue
    return tuple(sorted(pids))


def _descendant_pids(root_pid: int, include_children: bool) -> tuple[int, ...]:
    try:
        process = psutil.Process(root_pid)
        pids = {root_pid}
        if include_children:
            pids.update(child.pid for child in process.children(recursive=True))
        return tuple(sorted(pid for pid in pids if psutil.pid_exists(pid)))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ()


def _process_identity(pid: int) -> tuple[str | None, str | None, float | None]:
    try:
        process = psutil.Process(pid)
        command = " ".join(process.cmdline()) or process.name()
        username = process.username()
        started_at = process.create_time()
        return command, username, started_at
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None, None, None


def _parse_systemd_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    # psutil provides a more reliable epoch value when the leader is alive.
    return None


def _pid_from_values(values: dict[str, str], fallback: int = 0) -> int:
    for key in ("MainPID", "Leader"):
        try:
            value = int(values.get(key, "0"))
        except ValueError:
            continue
        if value > 0:
            return value
    return fallback


def _resolved_from_values(
    spec: TargetSpec,
    values: dict[str, str],
    *,
    manager: str,
    fallback_pid: int = 0,
    cgroup_hint: str | None = None,
) -> ResolvedTarget:
    canonical_unit = values.get("Id") or spec.value
    main_pid = _pid_from_values(values, fallback_pid)
    cgroup = values.get("ControlGroup") or cgroup_hint
    pids = _read_cgroup_pids(cgroup) if cgroup else ()
    if not pids and main_pid > 0:
        pids = _descendant_pids(main_pid, spec.include_children)

    command, username, started_at = (
        _process_identity(main_pid) if main_pid > 0 else (None, None, None)
    )
    if started_at is None:
        started_at = _parse_systemd_timestamp(values.get("ExecMainStartTimestamp"))

    try:
        restart_count = int(values.get("NRestarts", "0"))
    except ValueError:
        restart_count = None

    return ResolvedTarget(
        name=spec.name,
        kind="systemd",
        selector=spec.value,
        manager=manager,
        unit=canonical_unit,
        cgroup=cgroup,
        active_state=values.get("ActiveState") or "unknown",
        sub_state=values.get("SubState") or "unknown",
        main_pid=main_pid or None,
        pids=pids,
        command=command,
        user=username,
        started_at=started_at,
        unit_file_state=values.get("UnitFileState") or None,
        restart_count=restart_count,
    )


def _resolve_systemd(spec: TargetSpec, unit: str) -> ResolvedTarget | None:
    values = _run_systemctl_show(unit)
    if values is None:
        return None
    return _resolved_from_values(spec, values, manager="systemd")


def _resolve_membership(
    spec: TargetSpec,
    pid: int,
    membership: _SystemdMembership,
) -> ResolvedTarget:
    user_scope = membership.manager == "systemd-user"
    values = _run_systemctl_show(membership.unit, user_scope=user_scope)
    if values is not None:
        return _resolved_from_values(
            spec,
            values,
            manager=membership.manager,
            fallback_pid=pid,
            cgroup_hint=membership.cgroup,
        )

    pids = _read_cgroup_pids(membership.cgroup)
    if not pids:
        pids = _descendant_pids(pid, spec.include_children)
    command, username, started_at = _process_identity(pid)
    return ResolvedTarget(
        name=spec.name,
        kind="systemd",
        selector=spec.value,
        manager=membership.manager,
        unit=membership.unit,
        cgroup=membership.cgroup,
        active_state="active" if pids else "inactive",
        sub_state="running" if pids else "dead",
        main_pid=pid,
        pids=pids,
        command=command,
        user=username,
        started_at=started_at,
    )


def _matching_processes(needle: str) -> list[psutil.Process]:
    matches: list[psutil.Process] = []
    normalized = os.path.realpath(needle) if "/" in needle else needle
    for process in psutil.process_iter(["pid", "name", "exe", "cmdline", "ppid"]):
        try:
            name = process.info.get("name") or ""
            executable = process.info.get("exe") or ""
            cmdline = process.info.get("cmdline") or []
            executable_match = bool(executable) and os.path.realpath(executable) == normalized
            command_match = (
                bool(cmdline) and os.path.realpath(cmdline[0]) == normalized
                if "/" in needle
                else False
            )
            if name == needle or executable_match or command_match:
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return matches


def _root_matches(matches: Iterable[psutil.Process]) -> list[psutil.Process]:
    processes = list(matches)
    matched_pids = {process.pid for process in processes}
    roots: list[psutil.Process] = []
    for process in processes:
        try:
            if process.ppid() not in matched_pids:
                roots.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return roots


def _resolve_pid(spec: TargetSpec, pid: int, *, promote_systemd: bool = True) -> ResolvedTarget:
    if pid <= 0 or not psutil.pid_exists(pid):
        raise TargetResolutionError(f"PID {pid} does not exist")

    if promote_systemd:
        membership = _systemd_membership_from_pid(pid)
        if membership is not None:
            return _resolve_membership(spec, pid, membership)

    pids = _descendant_pids(pid, spec.include_children)
    command, username, started_at = _process_identity(pid)
    return ResolvedTarget(
        name=spec.name,
        kind="process",
        selector=spec.value,
        manager="none",
        main_pid=pid,
        pids=pids,
        command=command,
        user=username,
        started_at=started_at,
    )


class LinuxTargetResolver:
    def resolve(self, spec: TargetSpec) -> ResolvedTarget:
        if spec.kind == "systemd":
            unit = (
                spec.value
                if spec.value.endswith((".service", ".scope"))
                else f"{spec.value}.service"
            )
            resolved = _resolve_systemd(spec, unit)
            if resolved is None:
                raise TargetResolutionError(f"systemd unit {unit!r} was not found")
            return resolved

        if spec.kind == "pid":
            try:
                pid = int(spec.value)
            except ValueError as exc:
                raise TargetResolutionError(f"invalid PID: {spec.value!r}") from exc
            return _resolve_pid(spec, pid)

        if spec.kind == "pid_file":
            try:
                pid_text = Path(spec.value).read_text(encoding="utf-8").strip()
                return _resolve_pid(spec, int(pid_text))
            except (OSError, ValueError) as exc:
                raise TargetResolutionError(f"cannot read PID from {spec.value!r}: {exc}") from exc

        if spec.kind == "auto":
            candidates = [spec.value]
            if not spec.value.endswith((".service", ".scope")):
                candidates.append(f"{spec.value}.service")
            for unit in candidates:
                resolved = _resolve_systemd(spec, unit)
                if resolved is not None:
                    return resolved

            if spec.value.isdigit():
                return _resolve_pid(spec, int(spec.value))

        matches = _matching_processes(spec.value)
        roots = _root_matches(matches)
        if not roots:
            raise TargetResolutionError(f"no process or systemd service matched {spec.value!r}")
        if len(roots) > 1:
            choices = ", ".join(
                f"PID {process.pid} ({' '.join(process.cmdline()) or process.name()})"
                for process in roots[:8]
            )
            raise AmbiguousTargetError(
                f"target {spec.value!r} matched multiple process trees: {choices}"
            )
        return _resolve_pid(spec, roots[0].pid)
