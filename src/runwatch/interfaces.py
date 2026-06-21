from __future__ import annotations

from collections.abc import Iterable, Sequence
from types import TracebackType
from typing import Protocol, Self

from runwatch.results import CheckResult
from runwatch.targets.models import ResolvedTarget, TargetSnapshot, TargetSpec


class Check(Protocol):
    """A unit of monitoring work."""

    name: str
    check_type: str

    def run(self) -> CheckResult:
        """Run the check once and return a normalized result."""
        ...


class CheckRunner(Protocol):
    """Executes checks and yields results as they complete."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def run(self, checks: Sequence[Check]) -> Iterable[CheckResult]: ...


class ResultSink(Protocol):
    """Something that consumes check results."""

    def observe(self, result: CheckResult) -> None: ...


class MetricsServer(Protocol):
    """A metrics endpoint implementation."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class TargetResolver(Protocol):
    """Resolves a user selector into a process tree or systemd unit."""

    def resolve(self, spec: TargetSpec) -> ResolvedTarget: ...


class TargetSampler(Protocol):
    """Collects one cumulative resource snapshot for a resolved target."""

    def sample(self, target: ResolvedTarget) -> TargetSnapshot: ...


class TemplateGenerator(Protocol):
    """Generates deployment/config templates."""

    def render(self) -> str: ...
