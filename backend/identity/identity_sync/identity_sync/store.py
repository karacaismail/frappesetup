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

from identity_sync.deadline import bounded, bounded_for_records, remaining
from identity_sync.events import JOB_TYPES, REQUEST_KIND, USER_REMOVED_TYPES, Event

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
CREATE TABLE IF NOT EXISTS job_repeats (
    job_id TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    last_at REAL NOT NULL,
    claimed_until REAL NOT NULL
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
        # One connection serves every thread. A repeat of a deletion job writes without the work
        # lock (H-5), so the transactions of two threads must not interleave on the connection.
        self._db_lock = threading.RLock()
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
        # Inside a deadline the wait ends at the deadline too (inceleme 18).
        wait = bounded(self._lock_timeout)
        deadline = time.monotonic() + wait
        if not self._thread_lock.acquire(timeout=wait):
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
    def _transaction(self, *, bound: str = "") -> Iterator[None]:
        """A short write transaction. Roll back writes on error and always close the transaction.

        `bound` ties the waits for the connection and for the database file to the current deadline
        (inceleme 18 and 19). `Busy` is raised when the time is up.
        - `work`: a step before or between target calls. It ends at the deadline.
        - `record`: the record of an outcome. All records share one end, the deadline plus its grace.
        Without `bound`, or outside a deadline, the usual wait applies.
        """
        measure = {"work": bounded, "record": bounded_for_records}.get(bound)
        limited = measure is not None and remaining() is not None
        wait = measure(_SQLITE_TIMEOUT_SECONDS) if limited else _SQLITE_TIMEOUT_SECONDS
        if not self._db_lock.acquire(timeout=wait):
            raise Busy
        try:
            if limited:
                # The wait for the connection used part of the time. Measure again, so the wait
                # for the database file ends at the same deadline (inceleme 20).
                left = measure(_SQLITE_TIMEOUT_SECONDS)
                if left <= 0:
                    raise Busy
                self._db.execute(f"PRAGMA busy_timeout = {max(1, int(left * 1000))}")
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                if limited:
                    # Starting the write used part of the time. Measure again, so the wait to
                    # commit ends at the same deadline. Without time left the write is rolled
                    # back (inceleme 21).
                    left = measure(_SQLITE_TIMEOUT_SECONDS)
                    if left <= 0:
                        raise Busy
                    self._db.execute(f"PRAGMA busy_timeout = {max(1, int(left * 1000))}")
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
        except sqlite3.OperationalError as error:
            # The wait for another process ran out at the deadline.
            if limited and "locked" in str(error):
                raise Busy from None
            raise
        finally:
            if limited:
                self._db.execute(f"PRAGMA busy_timeout = {int(_SQLITE_TIMEOUT_SECONDS * 1000)}")
            self._db_lock.release()

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
        with self._transaction(bound="work"):
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
        with self._transaction(bound="work"):
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
        with self._transaction(bound="record"):
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
        with self._transaction(bound="record"):
            self._db.execute(
                "INSERT OR IGNORE INTO processed_events (event_id, status, processed_at) VALUES (?, ?, ?)",
                (event_id, status, self._clock()),
            )
            self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (event_id,))
            self._db.execute("DELETE FROM job_repeats WHERE job_id = ?", (event_id,))
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
        with self._transaction(bound="record"):
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

    def claim_repeat(
        self,
        job_id: str,
        *,
        hold: float,
        max_attempts: int | None = None,
        min_interval: float = 0.0,
    ) -> str:
        """Claim the right to run the steps of a queued account job (H-5). One transaction.

        The completion check is in the same transaction (inceleme 18). A job that another
        connection finished in the meantime cannot be claimed and run again.

        - `claimed`: the caller may run the job. The claim lasts `hold` seconds at most.
        - `done`: the job is finished. Nothing may run.
        - `busy`: another caller holds the claim. Two runs of one job never overlap, in this
          process or in another.
        - `limited`: the job ran `max_attempts` times, or its last claim is less than
          `min_interval` seconds old.

        `hold` keeps the claim after a run whose outcome is unknown: the target may still work on
        the call. The caller releases the claim only after a definite outcome.
        """
        now = self._clock()
        with self._transaction(bound="work"):
            if self._db.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (job_id,)).fetchone():
                return "done"
            row = self._db.execute(
                "SELECT attempts, last_at, claimed_until FROM job_repeats WHERE job_id = ?", (job_id,)
            ).fetchone()
            attempts = 0
            if row is not None:
                attempts, last_at, claimed_until = row
                if claimed_until > now:
                    return "busy"
                if max_attempts is not None and (attempts >= max_attempts or now - last_at < min_interval):
                    return "limited"
            self._db.execute(
                "INSERT OR REPLACE INTO job_repeats (job_id, attempts, last_at, claimed_until) VALUES (?, ?, ?, ?)",
                (job_id, attempts + 1, now, now + hold),
            )
        return "claimed"

    def repeatable_jobs(self, *, limit: int, max_attempts: int, min_interval: float) -> list[DeadLetter]:
        """Queued account jobs that `claim_repeat` would accept now, oldest first, at most `limit`.

        The database picks them, so a long queue is never read in full (inceleme 18).
        A finished, claimed or limited job is left out.
        """
        now = self._clock()
        placeholders = ", ".join("?" for _ in JOB_TYPES)
        rows = self._interruptible(
            f"""
            SELECT d.event, d.error, d.attempts, d.first_failed_at, d.last_failed_at, d.state
            FROM dead_letters AS d LEFT JOIN job_repeats AS r ON r.job_id = d.event_id
            WHERE json_extract(d.event, '$.type') IN ({placeholders})
              AND NOT EXISTS (SELECT 1 FROM processed_events AS p WHERE p.event_id = d.event_id)
              AND (r.job_id IS NULL OR (r.claimed_until <= ? AND r.attempts < ? AND ? - r.last_at >= ?))
            ORDER BY d.first_failed_at, d.event_id LIMIT ?
            """,  # only question marks are formatted into the text; every value is bound
            (*sorted(JOB_TYPES), now, max_attempts, now, min_interval, limit),
        )
        return [self._letter(*row) for row in rows]

    def _interruptible(self, sql: str, args: tuple[object, ...]) -> list[tuple]:
        """Run a read that stops at the current deadline (inceleme 19). `Busy` when the time is up.

        SQLite calls the handler every few thousand steps of the query. A non-zero answer stops the
        query. So a scan of a long queue with no matching job cannot run past the deadline.
        """
        if remaining() is None:
            return self._db.execute(sql, args).fetchall()
        if not self._db_lock.acquire(timeout=bounded(_SQLITE_TIMEOUT_SECONDS)):
            raise Busy
        try:
            # Measured after the connection lock: the wait for the database file ends at the same
            # deadline as the query (inceleme 20).
            left = bounded(_SQLITE_TIMEOUT_SECONDS)
            if left <= 0:
                raise Busy
            self._db.execute(f"PRAGMA busy_timeout = {max(1, int(left * 1000))}")
            self._db.set_progress_handler(lambda: 1 if not remaining() else 0, 1000)
            try:
                return self._db.execute(sql, args).fetchall()
            except sqlite3.OperationalError as error:
                if "interrupted" in str(error) or "locked" in str(error):
                    raise Busy from None
                raise
        finally:
            self._db.set_progress_handler(None, 0)
            self._db.execute(f"PRAGMA busy_timeout = {int(_SQLITE_TIMEOUT_SECONDS * 1000)}")
            self._db_lock.release()

    def extend_repeat(self, job_id: str, *, hold: float) -> None:
        """Let the claim of a job last `hold` seconds from now. Called before every external write.

        The claim then covers the last target call too, even when that call starts late in the
        request (inceleme 19). The claim never gets shorter here.
        """
        now = self._clock()
        with self._transaction(bound="work"):
            self._db.execute(
                "UPDATE job_repeats SET claimed_until = MAX(claimed_until, ?) WHERE job_id = ?", (now + hold, job_id)
            )

    def release_repeat(self, job_id: str) -> None:
        with self._transaction(bound="record"):
            self._db.execute("UPDATE job_repeats SET claimed_until = 0 WHERE job_id = ?", (job_id,))

    def repeat_claimed(self, job_id: str) -> bool:
        """Does another caller repeat the steps of this job right now?"""
        row = self._db.execute("SELECT claimed_until FROM job_repeats WHERE job_id = ?", (job_id,)).fetchone()
        return row is not None and row[0] > self._clock()

    def remove_dead_letter(self, event_id: str) -> None:
        with self._transaction(bound="record"):
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
        return [self._letter(*row) for row in rows]

    @staticmethod
    def _letter(event: str, error: str, attempts: int, first: float, last: float, state: str) -> DeadLetter:
        return DeadLetter(
            event=Event(**json.loads(event)),
            error=error,
            attempts=attempts,
            first_failed_at=first,
            last_failed_at=last,
            state=state,
        )

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
