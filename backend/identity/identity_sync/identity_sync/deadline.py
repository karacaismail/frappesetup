"""One end time for a piece of work, shared by the network, the store and the retry pauses.

`deadline(seconds, grace=...)` sets the end for the current thread. Name lookups, connections,
network reads, lock waits and retry pauses inside the block ask `remaining()` and never wait past
the end (H-5, inceleme 18 and 19). A nested block never moves an outer end later.

Writing the outcome of the work must still be possible right at the end. Those writes ask
`remaining_for_records()`: they share one later end, `grace` seconds after the deadline. All outcome
records of the block together wait at most that long. Outside a block both functions return None.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_END: ContextVar[tuple[float, float] | None] = ContextVar("identity_sync_deadline", default=None)


@contextmanager
def deadline(seconds: float, *, grace: float = 0.0) -> Iterator[None]:
    end = time.monotonic() + seconds
    outer = _END.get()
    if outer is not None:
        end = min(outer[0], end)
        grace = min(grace, max(0.0, outer[0] + outer[1] - end))
    token = _END.set((end, grace))
    try:
        yield
    finally:
        _END.reset(token)


def remaining() -> float | None:
    """Seconds left before the end, never below 0. None when no end applies."""
    current = _END.get()
    return None if current is None else max(0.0, current[0] - time.monotonic())


def remaining_for_records() -> float | None:
    """Seconds left for writing outcome records: until the end plus the grace. None without an end."""
    current = _END.get()
    return None if current is None else max(0.0, current[0] + current[1] - time.monotonic())


def bounded(wait: float) -> float:
    """The given wait, shortened to the time that is left."""
    left = remaining()
    return wait if left is None else min(wait, left)


def bounded_for_records(wait: float) -> float:
    """The given wait, shortened to the time that is left for outcome records."""
    left = remaining_for_records()
    return wait if left is None else min(wait, left)
