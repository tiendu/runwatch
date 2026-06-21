from __future__ import annotations


class DemoComposeTemplate:
    def render(self) -> str:
        return """# Demo only. For host monitoring, systemd install is preferred.
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
"""
