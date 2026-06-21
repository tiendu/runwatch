from __future__ import annotations

import argparse

from runwatch.doctor import doctor_to_json, render_doctor_report, run_doctor


def handle_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(
        config_path=args.config,
        metrics_address=args.metrics_address,
        metrics_port=args.metrics_port,
    )
    print(doctor_to_json(report) if args.json else render_doctor_report(report))
    return report.exit_code
