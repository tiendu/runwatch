from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrometheusScrapeTemplate:
    host: str = "localhost"
    port: int = 9109

    def render(self) -> str:
        return f"""scrape_configs:
  - job_name: runwatch
    static_configs:
      - targets: ['{self.host}:{self.port}']
"""


@dataclass(frozen=True)
class PrometheusAlertsTemplate:
    def render(self) -> str:
        return """groups:
  - name: runwatch
    rules:
      - alert: RunwatchCheckFailed
        expr: runwatch_check_up == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "runwatch check failed: {{ $labels.check_type }}/{{ $labels.name }}"

      - alert: RunwatchCheckWarning
        expr: runwatch_check_status == 1
        for: 5m
        labels:
          severity: info
        annotations:
          summary: "runwatch check warning: {{ $labels.check_type }}/{{ $labels.name }}"
"""
