from __future__ import annotations

import json

from runwatch.doctor import DoctorCheck, DoctorReport, doctor_to_json, render_doctor_report


def _report() -> DoctorReport:
    return DoctorReport(
        checks=(
            DoctorCheck("procfs", "pass", "readable"),
            DoctorCheck("eBPF", "info", "optional"),
            DoctorCheck("systemd user", "warn", "unavailable"),
        ),
        config_path=None,
        metrics_address="127.0.0.1",
        metrics_port=9109,
    )


def test_doctor_report_exit_code_and_rendering() -> None:
    report = _report()

    assert report.exit_code == 1
    output = render_doctor_report(report)
    assert "✓ procfs" in output
    assert "i eBPF" in output
    assert "! systemd user" in output
    assert "1 passed, 1 informational, 1 warning(s), 0 failure(s)" in output


def test_doctor_json_has_stable_schema() -> None:
    payload = json.loads(doctor_to_json(_report()))

    assert payload["schema_version"] == "1"
    assert payload["exit_code"] == 1
    assert payload["metrics_port"] == 9109
    assert payload["checks"][0]["name"] == "procfs"


def test_doctor_failure_wins_exit_code() -> None:
    report = DoctorReport(
        checks=(DoctorCheck("platform", "fail", "not Linux"),),
        config_path=None,
        metrics_address="127.0.0.1",
        metrics_port=9109,
    )

    assert report.exit_code == 2
