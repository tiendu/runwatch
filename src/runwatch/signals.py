from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event
from types import FrameType


@contextmanager
def shutdown_signals(stop_event: Event) -> Iterator[None]:
    """Set an event on SIGINT/SIGTERM and restore prior handlers afterward."""

    previous = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }

    def stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
