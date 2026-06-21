from runwatch.templates import SystemdUnitTemplate


def test_systemd_template_contains_execstart_and_hardening() -> None:
    unit = SystemdUnitTemplate(executable="/x/runwatch", config_path="/x/config.toml").render()

    assert "ExecStart=/x/runwatch serve --config /x/config.toml" in unit
    assert "Restart=on-failure" in unit
    assert "ProtectSystem=strict" in unit
    assert "NoNewPrivileges=true" in unit
    assert "User=root" in unit
