from __future__ import annotations

from time import perf_counter, sleep

import requests

from runwatch.config import HttpCheckConfig
from runwatch.results import CheckResult, MetricSample


class HttpCheck:
    check_type = "http"

    def __init__(self, config: HttpCheckConfig) -> None:
        self.config = config
        self.name = config.name

    def _metrics(
        self,
        *,
        up: int,
        request_duration_seconds: float,
        status_code: int | None,
    ) -> tuple[MetricSample, ...]:
        labels = {"name": self.name}
        metrics = [
            MetricSample(
                name="runwatch_http_up",
                help="Whether the HTTP endpoint passed its configured health check.",
                value=float(up),
                labels=labels,
            ),
            MetricSample(
                name="runwatch_http_request_duration_seconds",
                help="Duration of the last HTTP request attempt in seconds.",
                value=request_duration_seconds,
                labels=labels,
            ),
        ]
        if status_code is not None:
            metrics.append(
                MetricSample(
                    name="runwatch_http_status_code",
                    help="HTTP status code returned by the last request attempt.",
                    value=float(status_code),
                    labels=labels,
                )
            )
        return tuple(metrics)

    def run(self) -> CheckResult:
        check_started = perf_counter()
        last_error = ""
        last_request_duration = 0.0
        last_status_code: int | None = None
        attempts = self.config.retries + 1

        for attempt in range(1, attempts + 1):
            request_started = perf_counter()
            try:
                response = requests.get(self.config.url, timeout=self.config.timeout_seconds)
                last_request_duration = perf_counter() - request_started
                last_status_code = response.status_code
                status_ok = response.status_code == self.config.expected_status
                body_ok = (
                    self.config.expected_body is None or self.config.expected_body in response.text
                )

                if status_ok and body_ok:
                    return CheckResult(
                        check_type=self.check_type,
                        name=self.name,
                        status="ok",
                        message=f"HTTP {response.status_code}",
                        duration_seconds=perf_counter() - check_started,
                        labels={"url": self.config.url},
                        metrics=self._metrics(
                            up=1,
                            request_duration_seconds=last_request_duration,
                            status_code=last_status_code,
                        ),
                        details={"attempt": attempt},
                    )

                last_error = (
                    f"expected status {self.config.expected_status}, got {response.status_code}"
                    if not status_ok
                    else "expected body not found"
                )
            except requests.RequestException as exc:
                last_request_duration = perf_counter() - request_started
                last_error = f"{exc.__class__.__name__}: {exc}"

            if attempt < attempts:
                sleep(self.config.retry_delay_seconds)

        return CheckResult(
            check_type=self.check_type,
            name=self.name,
            status="fail",
            message=last_error or "HTTP check failed",
            duration_seconds=perf_counter() - check_started,
            labels={"url": self.config.url},
            metrics=self._metrics(
                up=0,
                request_duration_seconds=last_request_duration,
                status_code=last_status_code,
            ),
            details={"attempts": attempts},
        )
