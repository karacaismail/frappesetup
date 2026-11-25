# SPDX-License-Identifier: MIT
"""Durable inbox for external identity verification results (G-164).

The document and face check runs at an external provider. The provider is not chosen yet, so
the inbox is built with ``verifier=None`` and every call answers ``ConfigurationRequired``.

Order of work for each notice:
1. Check the signature over the raw request body, before any parsing.
2. Keep only the decision fields and store them once, keyed by the provider's event id.
3. ``process`` applies each stored notice once. A notice for an older attempt is kept as
   "stale" and does not change a newer decision.

Storage sits behind the ``NoticeStore`` interface. ``SqliteNoticeStore`` is the store of this
package. The Frappe store lives in ``platform_core`` (``PLT Verification Notice``), so this module
never imports Frappe.

There is no call that marks a case complete from the browser. Only a processed provider notice
changes a decision. Raw document and face data never reach the store.
The signature scheme below is a generic HMAC adapter. The chosen provider's own scheme replaces
it in an adapter with the same ``verify`` method.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping, Optional, Protocol, Tuple, Union, runtime_checkable

SIGNATURE_HEADER = "X-Verification-Signature"
DEFAULT_TOLERANCE_SECONDS = 300
OUTCOMES = {"approved", "rejected", "review"}
# Ids are kept in 140-character fields by the Frappe store. Every store refuses longer ids.
MAX_ID_LENGTH = 140
# An attempt with a final outcome keeps it. A later notice for the same attempt changes nothing.
FINAL_OUTCOMES = {"approved", "rejected"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
  case_id TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  PRIMARY KEY (case_id, attempt)
);
CREATE TABLE IF NOT EXISTS notices (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  case_id TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  outcome TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS decisions (
  case_id TEXT PRIMARY KEY,
  attempt INTEGER NOT NULL,
  outcome TEXT NOT NULL
);
"""


class ConfigurationRequired(RuntimeError):
    """No verification provider is configured. The check does not start."""


class SignatureRejected(ValueError):
    """The notice signature is missing, wrong or too old."""


class HmacSignature:
    """Generic adapter: header ``t=<unix seconds>,v1=<hex HMAC-SHA256 of '<t>.' + raw body>``."""

    def __init__(self, secret: bytes, tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS):
        if len(secret) < 32:
            raise ValueError("The signing secret must have at least 32 bytes.")
        self._secret = secret
        self._tolerance = tolerance_seconds

    def verify(self, raw_body: bytes, headers: Mapping[str, str], now: int) -> None:
        header = next((v for k, v in headers.items() if k.lower() == SIGNATURE_HEADER.lower()), "")
        pairs = [part.strip().split("=", 1) for part in header.split(",") if "=" in part]
        stamps = [value for key, value in pairs if key == "t"]
        signatures = [value for key, value in pairs if key == "v1"]
        try:
            (stamp_text,) = stamps
            stamp = int(stamp_text)
        except ValueError:
            raise SignatureRejected("The signature header is missing or malformed.") from None
        if not signatures:
            raise SignatureRejected("The signature header is missing or malformed.")
        if abs(now - stamp) > self._tolerance:
            raise SignatureRejected("The signature time is outside the allowed window.")
        expected = hmac.new(self._secret, str(stamp).encode() + b"." + raw_body, hashlib.sha256).hexdigest()
        # A provider may send several v1 values while it changes keys. One match is enough.
        wanted = expected.encode("ascii")
        if not any(hmac.compare_digest(wanted, given.encode("utf-8", "replace")) for given in signatures):
            raise SignatureRejected("The signature does not match the body.")


@runtime_checkable
class NoticeStore(Protocol):
    """Storage of attempts, notices and decisions. The inbox rules call only these methods.

    Attempts of a case are numbered 1, 2, 3 and so on without gaps, so the latest number is enough
    to know every attempt. ``transaction`` holds an exclusive write lock until it ends.
    """

    def transaction(self): ...

    def latest_attempt(self, case_id: str) -> int: ...

    def add_attempt(self, case_id: str, attempt: int) -> None: ...

    def add_notice(self, event_id: str, case_id: str, attempt: int, outcome: str) -> bool:
        """Store a new notice as pending. Returns False if the event id is already stored."""

    def next_pending(self) -> Optional[Tuple[object, str, str, int, str]]:
        """The oldest pending notice as ``(key, event_id, case_id, attempt, outcome)``, locked."""

    def set_state(self, key: object, state: str) -> None: ...

    def current_decision(self, case_id: str) -> Optional[Tuple[int, str]]: ...

    def set_decision(self, case_id: str, attempt: int, outcome: str) -> None: ...

    def requeue_unknown(self) -> int: ...

    def close(self) -> None: ...


class SqliteNoticeStore:
    """The package's own store: one SQLite file."""

    def __init__(self, path: Union[Path, str]):
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            yield

    def latest_attempt(self, case_id: str) -> int:
        (latest,) = self._db.execute(
            "SELECT COALESCE(MAX(attempt), 0) FROM attempts WHERE case_id = ?", (case_id,)
        ).fetchone()
        return latest

    def add_attempt(self, case_id: str, attempt: int) -> None:
        self._db.execute("INSERT INTO attempts (case_id, attempt) VALUES (?, ?)", (case_id, attempt))

    def add_notice(self, event_id: str, case_id: str, attempt: int, outcome: str) -> bool:
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO notices (event_id, case_id, attempt, outcome) VALUES (?, ?, ?, ?)",
            (event_id, case_id, attempt, outcome),
        )
        return cursor.rowcount == 1

    def next_pending(self):
        return self._db.execute(
            "SELECT sequence, event_id, case_id, attempt, outcome FROM notices "
            "WHERE state = 'pending' ORDER BY sequence LIMIT 1"
        ).fetchone()

    def set_state(self, key, state: str) -> None:
        self._db.execute("UPDATE notices SET state = ? WHERE sequence = ?", (state, key))

    def current_decision(self, case_id: str):
        return self._db.execute("SELECT attempt, outcome FROM decisions WHERE case_id = ?", (case_id,)).fetchone()

    def set_decision(self, case_id: str, attempt: int, outcome: str) -> None:
        self._db.execute(
            "INSERT INTO decisions (case_id, attempt, outcome) VALUES (?, ?, ?) "
            "ON CONFLICT(case_id) DO UPDATE SET attempt = excluded.attempt, outcome = excluded.outcome",
            (case_id, attempt, outcome),
        )

    def requeue_unknown(self) -> int:
        cursor = self._db.execute("UPDATE notices SET state = 'pending' WHERE state = 'unknown-attempt'")
        return cursor.rowcount


def _short_id(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= MAX_ID_LENGTH


class VerificationInbox:
    """The inbox rules. ``store`` is a ``NoticeStore``; a path opens a ``SqliteNoticeStore``.

    ``verifier`` checks signatures. Without one, ``open_attempt`` and ``receive`` answer
    ``ConfigurationRequired``. ``process`` needs no verifier: it applies notices already stored.
    """

    def __init__(self, store, verifier):
        self._verifier = verifier
        self._store = SqliteNoticeStore(store) if isinstance(store, (str, Path)) else store

    def close(self) -> None:
        self._store.close()

    def _configured(self) -> None:
        if self._verifier is None:
            raise ConfigurationRequired("No verification provider is configured.")

    def open_attempt(self, case_id: str) -> int:
        """Start a new attempt for a case. The newest attempt is the only one that can decide."""
        self._configured()
        if not _short_id(case_id):
            raise ValueError("The case id must be a non-empty text of at most 140 characters.")
        with self._store.transaction():
            attempt = self._store.latest_attempt(case_id) + 1
            self._store.add_attempt(case_id, attempt)
        return attempt

    def receive(self, raw_body: bytes, headers: Mapping[str, str], now: int) -> str:
        """Check and store one notice. Returns 'accepted' or 'duplicate'."""
        self._configured()
        self._verifier.verify(raw_body, headers, now)
        try:
            notice = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ValueError("The notice body is not JSON.") from None
        if not isinstance(notice, dict):
            raise ValueError("The notice body must be a JSON object.")
        event_id, case_id, attempt, outcome = (
            notice.get("event_id"), notice.get("case_id"), notice.get("attempt"), notice.get("outcome")
        )
        if not (_short_id(event_id) and _short_id(case_id)):
            raise ValueError("The notice needs event_id and case_id of at most 140 characters.")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("The notice needs a positive attempt number.")
        if outcome not in OUTCOMES:
            raise ValueError("The notice outcome is not known.")
        # Only these four fields are stored. Document images and face data in the body are dropped.
        return "accepted" if self._store.add_notice(event_id, case_id, attempt, outcome) else "duplicate"

    def process(self) -> list:
        """Apply every pending notice once, oldest first. Run by hand or by a queue worker."""
        done = []
        while True:
            with self._store.transaction():
                row = self._store.next_pending()
                if row is None:
                    return done
                key, event_id, case_id, attempt, outcome = row
                state = self._apply(case_id, attempt, outcome)
                self._store.set_state(key, state)
            done.append((event_id, state))

    def _apply(self, case_id: str, attempt: int, outcome: str) -> str:
        newest = self._store.latest_attempt(case_id)
        # Attempts have no gaps, so 1..newest are exactly the known attempts.
        if not 1 <= attempt <= newest:
            return "unknown-attempt"
        # Only the newest attempt decides. An older attempt's late result changes nothing.
        if attempt < newest:
            return "stale"
        current = self._store.current_decision(case_id)
        if current is not None and current[0] == attempt and current[1] in FINAL_OUTCOMES:
            return "final-kept"
        self._store.set_decision(case_id, attempt, outcome)
        return "applied"

    def replay_unknown(self) -> int:
        """Put notices for unknown attempts back in the queue. An operator runs this by hand."""
        return self._store.requeue_unknown()

    def decision(self, case_id: str) -> str:
        """The outcome of the newest attempt. A newer attempt without a result is 'pending'."""
        current = self._store.current_decision(case_id)
        if current is None or current[0] != self._store.latest_attempt(case_id):
            return "pending"
        return current[1]
