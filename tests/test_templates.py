from runwatch.templates import SystemdUnitTemplate


def test_systemd_template_contains_execstart_and_hardening() -> None:
    unit = SystemdUnitTemplate(executable="/x/runwatch", config_path="/x/config.toml").render()

    assert "ExecStart=/x/runwatch serve --config /x/config.toml" in unit
    assert "Restart=on-failure" in unit
    assert "ProtectSystem=strict" in unit
    assert "NoNewPrivileges=true" in unit
    assert "User=root" in unit


def test_systemd_template_quotes_paths_with_spaces() -> None:
    unit = SystemdUnitTemplate(
        executable="/opt/run watch/runwatch",
        config_path="/etc/run watch/runwatch.toml",
    ).render()

    assert (
        'ExecStart="/opt/run watch/runwatch" serve --config "/etc/run watch/runwatch.toml"' in unit
    )


def test_prometheus_template_quotes_target() -> None:
    from runwatch.templates import PrometheusScrapeTemplate

    payload = PrometheusScrapeTemplate(host="::1", port=9109).render()

    assert 'targets: ["::1:9109"]' in payload
