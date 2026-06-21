from __future__ import annotations

import json
from dataclasses import dataclass

from runwatch.defaults import DEFAULT_METRICS_PORT
from runwatch.errors import TemplateError


@dataclass(frozen=True)
class PrometheusScrapeTemplate:
    host: str = "localhost"
    port: int = DEFAULT_METRICS_PORT

    def render(self) -> str:
        host = self.host.strip()
        if not host or any(character.isspace() for character in host):
            raise TemplateError(
                "Prometheus target host must be non-empty and contain no whitespace"
            )
        if not 1 <= self.port <= 65535:
            raise TemplateError("Prometheus target port must be between 1 and 65535")
        target = json.dumps(f"{host}:{self.port}")
        return f"""scrape_configs:
  - job_name: runwatch
    static_configs:
      - targets: [{target}]
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
