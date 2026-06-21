from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event
from types import FrameType


@contextmanager
def handle_shutdown_signals(stop_event: Event) -> Iterator[None]:
    """Temporarily convert SIGINT and SIGTERM into a shutdown request.

    This context manager must be entered from the Python main thread.
    Previous handlers are restored when the context exits.
    """

    previous_handlers = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }

    def request_shutdown(
        _signum: int,
        _frame: FrameType | None,
    ) -> None:
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
