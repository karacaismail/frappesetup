"""One end time for a piece of work, shared by the network, the store and the retry pauses.

`deadline(seconds)` sets the end for the current thread. Network reads, lock waits and retry pauses
inside the block ask `remaining()` and never wait past the end (H-5, inceleme 18). A nested block
never moves an outer end later. Outside a block `remaining()` is None: no end applies.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_END: ContextVar[float | None] = ContextVar("identity_sync_deadline", default=None)


@contextmanager
def deadline(seconds: float) -> Iterator[None]:
    end = time.monotonic() + seconds
    outer = _END.get()
    token = _END.set(end if outer is None else min(outer, end))
    try:
        yield
    finally:
        _END.reset(token)


def remaining() -> float | None:
    """Seconds left before the end, never below 0. None when no end applies."""
    end = _END.get()
    return None if end is None else max(0.0, end - time.monotonic())


def bounded(wait: float) -> float:
    """The given wait, shortened to the time that is left."""
    left = remaining()
    return wait if left is None else min(wait, left)
