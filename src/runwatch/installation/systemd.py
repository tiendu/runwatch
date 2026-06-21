from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from runwatch.config import load_config, load_config_bytes
from runwatch.defaults import DEFAULT_CONFIG_PATH, DEFAULT_UNIT_PATH
from runwatch.errors import InstallationError, OutputError
from runwatch.filesystem import write_bytes_atomic, write_text_atomic
from runwatch.templates.systemd import SystemdUnitTemplate


@dataclass(frozen=True)
class _FileSnapshot:
    existed: bool
    content: bytes = b""
    mode: int | None = None


def _snapshot(path: Path) -> _FileSnapshot:
    if not path.exists() and not path.is_symlink():
        return _FileSnapshot(existed=False)
    try:
        return _FileSnapshot(
            existed=True,
            content=path.read_bytes(),
            mode=stat.S_IMODE(path.stat().st_mode),
        )
    except OSError as exc:
        raise InstallationError(f"cannot back up {path}: {exc}") from exc


def _restore(path: Path, snapshot: _FileSnapshot) -> None:
    if snapshot.existed:
        write_bytes_atomic(
            path,
            snapshot.content,
            overwrite=True,
            mode=snapshot.mode,
        )
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise InstallationError(f"cannot remove partially installed file {path}: {exc}") from exc


def _run_systemctl(*arguments: str, timeout: float = 30.0) -> None:
    try:
        result = subprocess.run(
            ["systemctl", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallationError(
            f"could not run systemctl {' '.join(arguments)}: {type(exc).__name__}: {exc}"
        ) from exc

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().replace("\n", " ")
        detail = message or f"exit status {result.returncode}"
        raise InstallationError(f"systemctl {' '.join(arguments)} failed: {detail}")


def _systemctl_is(state: str, unit: str, timeout: float = 10.0) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", state, "--quiet", unit],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallationError(
            f"could not query systemctl {state} {unit}: {type(exc).__name__}: {exc}"
        ) from exc
    return result.returncode == 0


def _best_effort_systemctl(arguments: tuple[str, ...], errors: list[str]) -> None:
    try:
        _run_systemctl(*arguments)
    except InstallationError as exc:
        errors.append(str(exc))


def _normalize_executable(executable: str, *, require_existing: bool) -> str:
    path = Path(executable).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if require_existing:
        if not path.is_file():
            raise InstallationError(f"runwatch executable does not exist: {path}")
        if not os.access(path, os.X_OK):
            raise InstallationError(f"runwatch executable is not executable: {path}")
    return str(path)


def _validate_destination(path: Path, description: str) -> None:
    if not path.is_absolute():
        raise InstallationError(f"{description} must be an absolute path: {path}")


def install_systemd_service(
    *,
    executable: str,
    config_source: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    unit_path: Path = DEFAULT_UNIT_PATH,
    enable: bool = True,
    force_unit: bool = False,
    force_config: bool = False,
    dry_run: bool = False,
) -> None:
    """Install Runwatch transactionally and optionally enable it.

    Config and unit files are restored if ``systemctl`` fails after either file
    has been changed.
    """

    if os.geteuid() != 0 and not dry_run:
        raise InstallationError("systemd installation must run as root")
    if not config_source.is_file():
        raise InstallationError(f"config source does not exist: {config_source}")

    # Read and validate one stable snapshot before making privileged changes.
    try:
        config_content = config_source.read_bytes()
    except OSError as exc:
        raise InstallationError(f"cannot read config source {config_source}: {exc}") from exc
    load_config_bytes(config_content, source=str(config_source))
    _validate_destination(config_path, "config destination")
    _validate_destination(unit_path, "systemd unit destination")
    if unit_path.suffix != ".service":
        raise InstallationError(f"systemd unit path must end in .service: {unit_path}")

    normalized_executable = _normalize_executable(
        executable,
        require_existing=not dry_run,
    )
    unit = SystemdUnitTemplate(
        config_path=str(config_path),
        executable=normalized_executable,
    ).render()

    unit_exists = unit_path.exists() or unit_path.is_symlink()
    if unit_exists and not force_unit:
        raise InstallationError(f"refusing to overwrite existing unit: {unit_path}")

    config_exists = config_path.exists() or config_path.is_symlink()
    config_will_change = not config_exists or force_config
    if not config_will_change:
        # Do not preserve a broken config and then start the service with it.
        load_config(config_path)

    if dry_run:
        config_action = "replace" if config_will_change else "keep"
        print(f"# would {config_action} config at {config_path}")
        print(f"# would write unit at {unit_path}")
        print(unit, end="" if unit.endswith("\n") else "\n")
        return

    previous_enabled = _systemctl_is("is-enabled", unit_path.name) if enable else False
    previous_active = _systemctl_is("is-active", unit_path.name) if enable else False

    config_snapshot = _snapshot(config_path)
    unit_snapshot = _snapshot(unit_path)
    config_changed = False
    unit_changed = False

    try:
        if config_will_change:
            write_bytes_atomic(
                config_path,
                config_content,
                overwrite=True,
                mode=0o640,
            )
            config_changed = True
        else:
            print(f"kept existing {config_path}")

        write_text_atomic(unit_path, unit, overwrite=True, mode=0o644)
        unit_changed = True

        _run_systemctl("daemon-reload")
        if enable:
            _run_systemctl("enable", "--now", unit_path.name)
    except (OSError, OutputError, InstallationError) as exc:
        rollback_errors: list[str] = []
        if unit_changed:
            try:
                _restore(unit_path, unit_snapshot)
            except InstallationError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if config_changed:
            try:
                _restore(config_path, config_snapshot)
            except InstallationError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if unit_changed:
            try:
                _run_systemctl("daemon-reload")
            except InstallationError as rollback_exc:
                rollback_errors.append(str(rollback_exc))

        if enable:
            if not previous_active:
                _best_effort_systemctl(("stop", unit_path.name), rollback_errors)
            if not previous_enabled:
                _best_effort_systemctl(("disable", unit_path.name), rollback_errors)

        message = str(exc)
        if rollback_errors:
            message += "; rollback issue(s): " + "; ".join(rollback_errors)
        raise InstallationError(message) from exc


__all__ = ["install_systemd_service"]
