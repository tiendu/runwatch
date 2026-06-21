from runwatch.targets.resolver import _membership_from_cgroup


def test_firefox_app_scope_beats_user_manager() -> None:
    membership = _membership_from_cgroup(
        "/user.slice/user-1000.slice/user@1000.service/app.slice/"
        "app-org.mozilla.firefox-12345.scope"
    )

    assert membership is not None
    assert membership.unit == "app-org.mozilla.firefox-12345.scope"
    assert membership.manager == "systemd-user"
    assert membership.cgroup.endswith("/app-org.mozilla.firefox-12345.scope")


def test_user_manager_is_not_a_monitoring_target() -> None:
    membership = _membership_from_cgroup(
        "/user.slice/user-1000.slice/user@1000.service/session.slice/session-3.scope"
    )

    assert membership is None


def test_system_service_is_detected() -> None:
    membership = _membership_from_cgroup("/system.slice/nginx.service")

    assert membership is not None
    assert membership.unit == "nginx.service"
    assert membership.manager == "systemd"
    assert membership.cgroup == "/system.slice/nginx.service"


def test_nested_user_service_is_detected() -> None:
    membership = _membership_from_cgroup(
        "/user.slice/user-1000.slice/user@1000.service/session.slice/pipewire.service"
    )

    assert membership is not None
    assert membership.unit == "pipewire.service"
    assert membership.manager == "systemd-user"


def test_parse_systemd_timestamp_microseconds() -> None:
    from runwatch.targets.resolver import _parse_systemd_timestamp

    assert _parse_systemd_timestamp("1700000000123456") == 1700000000.123456
    assert _parse_systemd_timestamp("0") is None
    assert _parse_systemd_timestamp("invalid") is None
