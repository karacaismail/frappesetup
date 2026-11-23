# SPDX-License-Identifier: MIT
"""Durable inbox for external identity verification results (G-164).

The document and face check runs at an external provider. The provider is not chosen yet, so
the inbox is built with ``verifier=None`` and every call answers ``ConfigurationRequired``.

Order of work for each notice:
1. Check the signature over the raw request body, before any parsing.
2. Keep only the decision fields and store them once, keyed by the provider's event id.
3. ``process`` applies each stored notice once. A notice for an older attempt is kept as
   "stale" and does not change a newer decision.

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
from pathlib import Path
from typing import Mapping

SIGNATURE_HEADER = "X-Verification-Signature"
DEFAULT_TOLERANCE_SECONDS = 300
OUTCOMES = {"approved", "rejected", "review"}
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


class VerificationInbox:
    def __init__(self, path: Path, verifier):
        self._verifier = verifier
        self._db = sqlite3.connect(str(path), isolation_level=None)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _configured(self) -> None:
        if self._verifier is None:
            raise ConfigurationRequired("No verification provider is configured.")

    def open_attempt(self, case_id: str) -> int:
        """Start a new attempt for a case. The newest attempt is the only one that can decide."""
        self._configured()
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            (latest,) = self._db.execute(
                "SELECT COALESCE(MAX(attempt), 0) FROM attempts WHERE case_id = ?", (case_id,)
            ).fetchone()
            self._db.execute("INSERT INTO attempts (case_id, attempt) VALUES (?, ?)", (case_id, latest + 1))
        return latest + 1

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
        if not (isinstance(event_id, str) and event_id and isinstance(case_id, str) and case_id):
            raise ValueError("The notice needs event_id and case_id.")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("The notice needs a positive attempt number.")
        if outcome not in OUTCOMES:
            raise ValueError("The notice outcome is not known.")
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO notices (event_id, case_id, attempt, outcome) VALUES (?, ?, ?, ?)",
            (event_id, case_id, attempt, outcome),
        )
        return "accepted" if cursor.rowcount == 1 else "duplicate"

    def process(self) -> list:
        """Apply every pending notice once, oldest first. Run by hand or by a queue worker."""
        done = []
        while True:
            with self._db:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT sequence, event_id, case_id, attempt, outcome FROM notices "
                    "WHERE state = 'pending' ORDER BY sequence LIMIT 1"
                ).fetchone()
                if row is None:
                    return done
                sequence, event_id, case_id, attempt, outcome = row
                state = self._apply(case_id, attempt, outcome)
                self._db.execute("UPDATE notices SET state = ? WHERE sequence = ?", (state, sequence))
            done.append((event_id, state))

    def _apply(self, case_id: str, attempt: int, outcome: str) -> str:
        known = self._db.execute(
            "SELECT 1 FROM attempts WHERE case_id = ? AND attempt = ?", (case_id, attempt)
        ).fetchone()
        if known is None:
            return "unknown-attempt"
        # Only the newest attempt decides. An older attempt's late result changes nothing.
        (newest,) = self._db.execute("SELECT MAX(attempt) FROM attempts WHERE case_id = ?", (case_id,)).fetchone()
        if attempt < newest:
            return "stale"
        current = self._db.execute(
            "SELECT attempt, outcome FROM decisions WHERE case_id = ?", (case_id,)
        ).fetchone()
        if current is not None and current[0] == attempt and current[1] in FINAL_OUTCOMES:
            return "final-kept"
        self._db.execute(
            "INSERT INTO decisions (case_id, attempt, outcome) VALUES (?, ?, ?) "
            "ON CONFLICT(case_id) DO UPDATE SET attempt = excluded.attempt, outcome = excluded.outcome",
            (case_id, attempt, outcome),
        )
        return "applied"

    def replay_unknown(self) -> int:
        """Put notices for unknown attempts back in the queue. An operator runs this by hand."""
        cursor = self._db.execute("UPDATE notices SET state = 'pending' WHERE state = 'unknown-attempt'")
        return cursor.rowcount

    def decision(self, case_id: str) -> str:
        """The outcome of the newest attempt. A newer attempt without a result is 'pending'."""
        row = self._db.execute(
            "SELECT d.outcome FROM decisions d WHERE d.case_id = ? AND d.attempt = "
            "(SELECT MAX(attempt) FROM attempts WHERE case_id = d.case_id)",
            (case_id,),
        ).fetchone()
        return row[0] if row else "pending"
