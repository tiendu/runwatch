from __future__ import annotations

from runwatch.execution import dispatch_result
from runwatch.results import CheckResult


class BrokenSink:
    def observe(self, _result: CheckResult) -> None:
        raise RuntimeError("sink failed")


class RecordingSink:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def observe(self, result: CheckResult) -> None:
        self.results.append(result)


def test_sink_failure_does_not_block_other_sinks() -> None:
    result = CheckResult(
        check_type="test",
        name="sample",
        status="ok",
        message="ok",
        duration_seconds=0.1,
    )
    recording = RecordingSink()

    dispatch_result(result, [BrokenSink(), recording])

    assert recording.results == [result]
