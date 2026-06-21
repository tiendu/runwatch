from __future__ import annotations

from pathlib import Path

import pytest

from runwatch.errors import InstallationError
from runwatch.installation import systemd as systemd_module


def _valid_config(path: Path) -> None:
    path.write_text(
        """
[system]
enabled = true
disk_paths = ["/"]
""",
        encoding="utf-8",
    )


def test_install_rolls_back_files_when_enable_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "runwatch"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)

    source = tmp_path / "source.toml"
    _valid_config(source)
    config_path = tmp_path / "etc" / "runwatch.toml"
    config_path.parent.mkdir()
    config_path.write_text("[system]\nenabled = false\n", encoding="utf-8")
    unit_path = tmp_path / "systemd" / "runwatch.service"
    unit_path.parent.mkdir()
    unit_path.write_text("old unit\n", encoding="utf-8")

    monkeypatch.setattr(systemd_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(systemd_module, "_systemctl_is", lambda _state, _unit: False)

    def fake_systemctl(*arguments: str, timeout: float = 30.0) -> None:
        del timeout
        if arguments[:2] == ("enable", "--now"):
            raise InstallationError("start failed")

    monkeypatch.setattr(systemd_module, "_run_systemctl", fake_systemctl)

    with pytest.raises(InstallationError, match="start failed"):
        systemd_module.install_systemd_service(
            executable=str(executable),
            config_source=source,
            config_path=config_path,
            unit_path=unit_path,
            force_unit=True,
            force_config=True,
            enable=True,
        )

    assert config_path.read_text(encoding="utf-8") == "[system]\nenabled = false\n"
    assert unit_path.read_text(encoding="utf-8") == "old unit\n"


def test_install_refuses_existing_unit_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "runwatch"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    source = tmp_path / "source.toml"
    _valid_config(source)
    config_path = tmp_path / "runwatch.toml"
    unit_path = tmp_path / "runwatch.service"
    unit_path.write_text("existing", encoding="utf-8")

    monkeypatch.setattr(systemd_module.os, "geteuid", lambda: 0)

    with pytest.raises(InstallationError, match="refusing to overwrite"):
        systemd_module.install_systemd_service(
            executable=str(executable),
            config_source=source,
            config_path=config_path,
            unit_path=unit_path,
        )
