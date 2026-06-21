from time import perf_counter, sleep

from runwatch.results import CheckResult
from runwatch.runner import ThreadedCheckRunner


class SlowCheck:
    check_type = "test"

    def __init__(self, name: str, delay: float) -> None:
        self.name = name
        self.delay = delay

    def run(self) -> CheckResult:
        sleep(self.delay)
        return CheckResult(
            check_type=self.check_type,
            name=self.name,
            status="ok",
            message="ok",
            duration_seconds=self.delay,
        )


def test_threaded_runner_runs_checks_concurrently() -> None:
    started = perf_counter()
    with ThreadedCheckRunner(max_workers=2) as runner:
        results = list(runner.run([SlowCheck("a", 0.12), SlowCheck("b", 0.12)]))
    elapsed = perf_counter() - started

    assert {result.name for result in results} == {"a", "b"}
    assert elapsed < 0.22
