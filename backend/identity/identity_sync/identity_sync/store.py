"""Persistent record: processed events, the dead-letter queue, used signatures and approvals,
and the journal of multi-step operations.

The record is a SQLite file. SQLite is in Python's own library.
The record holds no e-mail and no name. It does hold the Keycloak user id (`sub`), which the
project record counts as personal data. The id is kept only while the work needs it:

- a queued event keeps it until the event is processed, then the row is deleted,
- an operation journal row drops it when the operation is done or resolved,
- when an account deletion job finishes, every remaining row of that user drops it.

The id of a finished event or job stays as a duplicate guard. A job id is a keyed digest.

There are two separate protections:

- Each record write is a short database transaction and becomes durable immediately.
  Completed work remains recorded if the process stops halfway through.
- `work_lock()` serializes event processing. The server and `replay-dead-letters` command
  run in separate processes. A lock file uses `flock`, which is released automatically when the process dies.
  The lock does not lock the database, so signature claims and reads do not wait for long operations.
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from identity_sync.events import REQUEST_KIND, USER_REMOVED_TYPES, Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    processed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dead_letters (
    event_id TEXT PRIMARY KEY,
    event TEXT NOT NULL,
    error TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL,
    first_failed_at REAL NOT NULL,
    last_failed_at REAL NOT NULL,
    finished_steps TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS used_signatures (
    signature TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    subject TEXT,
    steps TEXT NOT NULL,
    state TEXT NOT NULL,
    resolution TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS used_approvals (
    approval_id TEXT PRIMARY KEY,
    preview_digest TEXT NOT NULL,
    operation TEXT NOT NULL,
    used_at REAL NOT NULL
);
"""

STATES = ("failed", "unknown")
_LOCK_POLL_SECONDS = 0.02
_SQLITE_TIMEOUT_SECONDS = 5.0


class Busy(Exception):
    """Another process holds the work lock and the wait timed out."""


@dataclass(frozen=True)
class DeadLetter:
    """`state` is either `failed` or `unknown`.

    `failed`: the target rejected the work or was unreachable. `unknown`: completion is unknown.
    """

    event: Event
    error: str
    attempts: int
    first_failed_at: float
    last_failed_at: float
    state: str = "failed"

    def to_dict(self) -> dict[str, object]:
        event = self.event.to_dict()
        if self.event.kind == REQUEST_KIND or self.event.type in USER_REMOVED_TYPES:
            # An account job is named by its id, a keyed digest. The listing does not show whose
            # it is. The same holds for a Keycloak delete event: its account is, or is being, deleted.
            event.pop("user_id", None)
        return {
            "event": event,
            "error": self.error,
            "state": self.state,
            "attempts": self.attempts,
            "first_failed_at": self.first_failed_at,
            "last_failed_at": self.last_failed_at,
        }


class Store:
    def __init__(self, path: str, *, clock: Callable[[], float] = time.time, lock_timeout: float = 10.0) -> None:
        """`lock_timeout` is the maximum wait for the work lock, in seconds."""
        self._clock = clock
        self._lock_timeout = lock_timeout
        self._lock_fd: int | None = None
        if path != ":memory:":
            # Allow only the service user to read the files.
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
            os.chmod(path, 0o600)
            self._lock_fd = os.open(f"{path}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        # Each write has a short transaction (`isolation_level=None`: this class manages transactions).
        self._db = sqlite3.connect(
            path, timeout=_SQLITE_TIMEOUT_SECONDS, isolation_level=None, check_same_thread=False
        )
        self._thread_lock = threading.Lock()
        self._db.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add the missing column to a store file from an older version."""
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(dead_letters)")}
        missing = {
            "state": "TEXT NOT NULL DEFAULT 'failed'",
            "finished_steps": "TEXT NOT NULL DEFAULT '[]'",
        }
        for name, definition in missing.items():
            if name not in columns:
                with self._transaction():
                    self._db.execute(f"ALTER TABLE dead_letters ADD COLUMN {name} {definition}")

    def close(self) -> None:
        self._db.close()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    @contextmanager
    def work_lock(self) -> Iterator[None]:
        """Serialize event processing. Other processes and connections wait.

        Raise `Busy` if the wait exceeds `lock_timeout`. The lock does not roll back records.
        Every record written under the lock becomes durable immediately.
        """
        deadline = time.monotonic() + self._lock_timeout
        if not self._thread_lock.acquire(timeout=self._lock_timeout):
            raise Busy
        try:
            if self._lock_fd is not None:
                while True:
                    try:
                        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise Busy from None
                        time.sleep(_LOCK_POLL_SECONDS)
            try:
                yield
            finally:
                if self._lock_fd is not None:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            self._thread_lock.release()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """A short write transaction. Roll back writes on error and always close the transaction."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def is_processed(self, event_id: str) -> bool:
        row = self._db.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)).fetchone()
        return row is not None

    def dead_letter_state(self, event_id: str) -> str | None:
        """Return the event state if it is in the dead-letter queue, otherwise `None`."""
        row = self._db.execute("SELECT state FROM dead_letters WHERE event_id = ?", (event_id,)).fetchone()
        return row[0] if row else None

    def begin(self, event: Event) -> None:
        """Record an accepted event before any work starts.

        If the process dies before the outcome is recorded, the event stays in the queue and
        can be replayed by hand. An event that is already in the queue keeps its record.
        The row counts no attempt yet.
        """
        now = self._clock()
        with self._transaction():
            self._db.execute(
                """
                INSERT OR IGNORE INTO dead_letters
                    (event_id, event, error, state, attempts, first_failed_at, last_failed_at)
                VALUES (?, ?, 'accepted; outcome not recorded', 'failed', 0, ?, ?)
                """,
                (event.id, json.dumps(event.to_dict()), now, now),
            )

    def mark_writing(self, event_id: str) -> None:
        """Mark the event `unknown` right before its first external write.

        From here on a crash leaves the outcome unknown: a target may have done the write.
        The record is corrected once the outcome is known.
        """
        with self._transaction():
            self._db.execute(
                "UPDATE dead_letters SET state = 'unknown', error = 'interrupted after a write was started' "
                "WHERE event_id = ?",
                (event_id,),
            )

    def progress(self, event_id: str) -> frozenset[str]:
        """Keys of the steps of an ordered plan that are finished. A key is a keyed digest of the step."""
        row = self._db.execute("SELECT finished_steps FROM dead_letters WHERE event_id = ?", (event_id,)).fetchone()
        return frozenset(json.loads(row[0])) if row else frozenset()

    def add_progress(self, event_id: str, step_key: str) -> None:
        """Record one finished step. Written after each step, so a retry never calls it again."""
        with self._transaction():
            row = self._db.execute("SELECT finished_steps FROM dead_letters WHERE event_id = ?", (event_id,)).fetchone()
            if row is None:
                return
            steps = sorted({*json.loads(row[0]), step_key})
            self._db.execute("UPDATE dead_letters SET finished_steps = ? WHERE event_id = ?", (json.dumps(steps), event_id))

    def claim_approval(
        self,
        approval_id: str,
        preview_digest: str,
        operation: str,
        *,
        journal: tuple[str, list[str]] | None = None,
    ) -> bool:
        """Consume a human approval. Returns False when the approval was used before.

        An approval works once and belongs to the preview digest it was first used with.
        The claim is written before any external write starts.

        `journal` is `(organization_id, steps)`. The operation journal is then opened in the
        same transaction. A crash right after the claim cannot leave a spent approval with no
        record of the work it was spent on.
        """
        now = self._clock()
        with self._transaction():
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO used_approvals (approval_id, preview_digest, operation, used_at) "
                "VALUES (?, ?, ?, ?)",
                (approval_id, preview_digest, operation, now),
            )
            if cursor.rowcount != 1:
                return False
            if journal is not None:
                organization_id, steps = journal
                plan = json.dumps([{"step": step, "status": "pending"} for step in steps])
                self._db.execute(
                    "INSERT INTO operations "
                    "(operation_id, operation, organization_id, steps, state, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'running', ?, ?)",
                    (approval_id, operation, organization_id, plan, now, now),
                )
            return True

    # --- operation journal: multi-step writes that are not events (for example an invitation) ---

    def operation_begin(self, operation_id: str, operation: str, organization_id: str, steps: list[str]) -> None:
        """Record an operation and its planned steps before the first write.

        The record holds ids only. It stores no e-mail.
        """
        now = self._clock()
        plan = json.dumps([{"step": step, "status": "pending"} for step in steps])
        with self._transaction():
            self._db.execute(
                "INSERT INTO operations (operation_id, operation, organization_id, steps, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'running', ?, ?)",
                (operation_id, operation, organization_id, plan, now, now),
            )

    def operation_step(self, operation_id: str, step: str, status: str, *, subject: str | None = None) -> None:
        """Record a step's status. `writing` is written before the request leaves.

        A step left at `writing` means the process stopped mid-write: its outcome is unknown.
        """
        if status not in ("writing", "done", "failed", "unknown"):
            raise ValueError("invalid step status")
        with self._transaction():
            row = self._db.execute("SELECT steps FROM operations WHERE operation_id = ?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            steps = json.loads(row[0])
            for item in steps:
                if item["step"] == step:
                    item["status"] = status
            self._db.execute(
                "UPDATE operations SET steps = ?, subject = COALESCE(?, subject), updated_at = ? WHERE operation_id = ?",
                (json.dumps(steps), subject, self._clock(), operation_id),
            )

    def operation_subject(self, operation_id: str, subject: str) -> None:
        """Record the Keycloak id of the user the operation works on."""
        with self._transaction():
            self._db.execute(
                "UPDATE operations SET subject = ?, updated_at = ? WHERE operation_id = ?",
                (subject, self._clock(), operation_id),
            )

    def operation_finish(self, operation_id: str, state: str) -> None:
        if state not in ("done", "failed", "unknown"):
            raise ValueError("invalid operation state")
        with self._transaction():
            self._db.execute(
                "UPDATE operations SET state = ?, updated_at = ? WHERE operation_id = ?",
                (state, self._clock(), operation_id),
            )
            if state == "done":
                # Nothing is left to settle, so the row no longer needs to name the user.
                self._db.execute("UPDATE operations SET subject = '' WHERE operation_id = ?", (operation_id,))

    def forget_subject(self, subject: str) -> None:
        """Remove a user's id from the operation journal. Called when the account deletion is done."""
        with self._transaction():
            self._db.execute("UPDATE operations SET subject = '' WHERE subject = ?", (subject,))

    def operations(self, *, limit: int | None = None, offset: int = 0) -> list[dict[str, object]]:
        """Unfinished operations, oldest first. A human checks the target and resolves each one."""
        rows = self._db.execute(
            "SELECT operation_id, operation, organization_id, subject, steps, state FROM operations "
            "WHERE state NOT IN ('done', 'resolved') ORDER BY created_at, operation_id LIMIT ? OFFSET ?",
            (-1 if limit is None else limit, offset),
        ).fetchall()
        result = []
        for operation_id, operation, organization_id, subject, steps, state in rows:
            parsed = json.loads(steps)
            for item in parsed:
                if item["status"] == "writing":
                    item["status"] = "unknown"  # started, never finished
            if state == "running":
                state = "unknown"  # the process stopped before it recorded the end
            result.append(
                {
                    "operation_id": operation_id,
                    "operation": operation,
                    "organization_id": organization_id,
                    "subject": subject,
                    "state": state,
                    "steps": parsed,
                }
            )
        return result

    def operation_organization(self, operation_id: str) -> str | None:
        """Return the immutable organization binding before authorizing a resolution."""
        row = self._db.execute(
            "SELECT organization_id FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        return row[0] if row is not None else None

    def operation_resolve(self, operation_id: str, resolution: str) -> bool:
        """Close an unfinished operation after a human settled it on the target. False if there is none."""
        with self._transaction():
            cursor = self._db.execute(
                "UPDATE operations SET state = 'resolved', resolution = ?, subject = '', updated_at = ? "
                "WHERE operation_id = ? AND state NOT IN ('done', 'resolved')",
                (resolution, self._clock(), operation_id),
            )
            return cursor.rowcount == 1

    def mark_processed(self, event_id: str, status: str, *, forget_subject: str | None = None) -> None:
        """Count the event as processed and take it out of the queue. One transaction.

        `forget_subject`: the account of this user is deleted. In the same transaction every
        record that still names the user drops the id: the operation journal and any other
        queued event of that user. Either the job is finished and no record names the user, or
        neither happened and a retry does both. A finished job can never leave the id behind.
        """
        with self._transaction():
            self._db.execute(
                "INSERT OR IGNORE INTO processed_events (event_id, status, processed_at) VALUES (?, ?, ?)",
                (event_id, status, self._clock()),
            )
            self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (event_id,))
            if forget_subject:
                self._db.execute("UPDATE operations SET subject = '' WHERE subject = ?", (forget_subject,))
                queued = self._db.execute("SELECT event_id, event FROM dead_letters").fetchall()
                for queued_id, raw in queued:
                    if json.loads(raw).get("user_id") == forget_subject:
                        # Work for an account that no longer exists. It must not keep the id.
                        self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (queued_id,))

    def add_dead_letter(self, event: Event, error: str, *, state: str = "failed") -> None:
        """Write the event to the dead-letter queue. Increment attempts if it is already queued."""
        if state not in STATES:
            raise ValueError("invalid dead letter state")
        now = self._clock()
        with self._transaction():
            self._db.execute(
                """
                INSERT INTO dead_letters (event_id, event, error, state, attempts, first_failed_at, last_failed_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    error = excluded.error,
                    state = excluded.state,
                    attempts = attempts + 1,
                    last_failed_at = excluded.last_failed_at
                """,
                (event.id, json.dumps(event.to_dict()), error, state, now, now),
            )

    def remove_dead_letter(self, event_id: str) -> None:
        with self._transaction():
            self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (event_id,))

    def dead_letters(self, *, limit: int | None = None, offset: int = 0) -> list[DeadLetter]:
        """The queue, oldest first. The event id breaks ties, so paging is stable.

        Without `limit` the whole queue is read. Only the replay does that: it must see every
        event. A listing for a caller always passes a limit.
        """
        rows = self._db.execute(
            "SELECT event, error, attempts, first_failed_at, last_failed_at, state FROM dead_letters "
            "ORDER BY first_failed_at, event_id LIMIT ? OFFSET ?",
            (-1 if limit is None else limit, offset),
        ).fetchall()
        return [
            DeadLetter(
                event=Event(**json.loads(event)),
                error=error,
                attempts=attempts,
                first_failed_at=first,
                last_failed_at=last,
                state=state,
            )
            for event, error, attempts, first, last, state in rows
        ]

    def claim_signature(self, signature: str, *, now: float, expires_at: float) -> bool:
        """Record a signature as used. Return `False` if it was used before.

        `now` comes from the clock used to check the time window. Remove expired records
        during this call. The time window already rejects those signatures.
        """
        with self._transaction():
            self._db.execute("DELETE FROM used_signatures WHERE expires_at < ?", (now,))
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO used_signatures (signature, expires_at) VALUES (?, ?)", (signature, expires_at)
            )
            return cursor.rowcount == 1
