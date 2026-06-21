from __future__ import annotations

from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import TracebackType

from runwatch.execution import execute_check
from runwatch.interfaces import Check
from runwatch.results import CheckResult


class SequentialCheckRunner:
    def __enter__(self) -> SequentialCheckRunner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def run(self, checks: Sequence[Check]) -> Iterable[CheckResult]:
        for check in checks:
            yield execute_check(check)


class ThreadedCheckRunner:
    def __init__(self, max_workers: int) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be greater than zero")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="runwatch-check",
        )

    def __enter__(self) -> ThreadedCheckRunner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    def run(self, checks: Sequence[Check]) -> Iterable[CheckResult]:
        futures = [self._executor.submit(execute_check, check) for check in checks]
        for future in as_completed(futures):
            yield future.result()
