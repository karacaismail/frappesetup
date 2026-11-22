"""Kalıcı kayıt: işlenen olaylar, bekleme kuyruğu ve kullanılmış imzalar.

Kayıt SQLite dosyasında durur. SQLite Python'un kendi kitaplığındadır.
Kayıt kişisel veri taşımaz. Olayın yalnız kimlik alanları saklanır.

İki ayrı koruma vardır:

- Her kayıt yazısı kısa bir veritabanı işlemidir ve hemen kalıcı olur.
  Süreç yarıda durursa biten işlerin kaydı kaybolmaz.
- `work_lock()` bir olayın işini sıraya koyar. Sunucu ve `replay-dead-letters` komutu
  ayrı süreçlerdir. Kilit bir kilit dosyasındadır (`flock`). Süreç ölürse kilit kendiliğinden açılır.
  Kilit veritabanını kilitlemez. Bu yüzden imza kaydı ve okuma uzun süren işi beklemez.
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

from identity_sync.events import Event

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
    last_failed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS used_signatures (
    signature TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
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
    """Başka bir süreç iş kilidini tutuyor ve bekleme süresi doldu."""


@dataclass(frozen=True)
class DeadLetter:
    """`state` değeri `failed` ya da `unknown` olur.

    `failed`: hedef işi reddetti ya da ulaşılamadı. `unknown`: işin bitip bitmediği bilinmiyor.
    """

    event: Event
    error: str
    attempts: int
    first_failed_at: float
    last_failed_at: float
    state: str = "failed"

    def to_dict(self) -> dict[str, object]:
        return {
            "event": self.event.to_dict(),
            "error": self.error,
            "state": self.state,
            "attempts": self.attempts,
            "first_failed_at": self.first_failed_at,
            "last_failed_at": self.last_failed_at,
        }


class Store:
    def __init__(self, path: str, *, clock: Callable[[], float] = time.time, lock_timeout: float = 10.0) -> None:
        """`lock_timeout`, iş kilidini beklemenin en uzun süresidir. Birim saniyedir."""
        self._clock = clock
        self._lock_timeout = lock_timeout
        self._lock_fd: int | None = None
        if path != ":memory:":
            # Dosyaları yalnız servisin kullanıcısı okuyabilsin.
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
            os.chmod(path, 0o600)
            self._lock_fd = os.open(f"{path}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        # Her yazı kendi kısa işlemindedir (`isolation_level=None`: işlemi bu sınıf yönetir).
        self._db = sqlite3.connect(
            path, timeout=_SQLITE_TIMEOUT_SECONDS, isolation_level=None, check_same_thread=False
        )
        self._thread_lock = threading.Lock()
        self._db.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Eski sürümün kayıt dosyasına eksik sütunu ekler."""
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(dead_letters)")}
        if "state" not in columns:
            with self._transaction():
                self._db.execute("ALTER TABLE dead_letters ADD COLUMN state TEXT NOT NULL DEFAULT 'failed'")

    def close(self) -> None:
        self._db.close()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    @contextmanager
    def work_lock(self) -> Iterator[None]:
        """Bir olayın işini sıraya koyar. Öteki süreçler ve bağlantılar bekler.

        Bekleme `lock_timeout` süresini aşarsa `Busy` yükselir. Kilit kayıtları geri almaz.
        Kilit altında yazılan her kayıt hemen kalıcıdır.
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
        """Kısa bir yazma işlemi. Hata olursa yazılar geri alınır. İşlem açık kalmaz."""
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
        """Olay bekleme kuyruğundaysa durumunu döner. Değilse `None` döner."""
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

    def claim_approval(self, approval_id: str, preview_digest: str, operation: str) -> bool:
        """Consume a human approval. Returns False when the approval was used before.

        An approval works once and belongs to the preview digest it was first used with.
        The claim is written before any external write starts.
        """
        with self._transaction():
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO used_approvals (approval_id, preview_digest, operation, used_at) "
                "VALUES (?, ?, ?, ?)",
                (approval_id, preview_digest, operation, self._clock()),
            )
            return cursor.rowcount == 1

    def mark_processed(self, event_id: str, status: str) -> None:
        """Olayı işlenmiş sayar ve bekleme kuyruğundan çıkarır. İki yazı tek işlemdedir."""
        with self._transaction():
            self._db.execute(
                "INSERT OR IGNORE INTO processed_events (event_id, status, processed_at) VALUES (?, ?, ?)",
                (event_id, status, self._clock()),
            )
            self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (event_id,))

    def add_dead_letter(self, event: Event, error: str, *, state: str = "failed") -> None:
        """Olayı bekleme kuyruğuna yazar. Olay zaten kuyruktaysa deneme sayısını artırır."""
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

    def dead_letters(self) -> list[DeadLetter]:
        rows = self._db.execute(
            "SELECT event, error, attempts, first_failed_at, last_failed_at, state FROM dead_letters "
            "ORDER BY first_failed_at, event_id"
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
        """İmzayı kullanılmış diye kaydeder. İmza daha önce kullanıldıysa `False` döner.

        `now`, zaman penceresini denetleyen saatin değeridir. Süresi dolan kayıtlar bu
        çağrıda silinir. Zaman penceresi o imzaları zaten reddeder.
        """
        with self._transaction():
            self._db.execute("DELETE FROM used_signatures WHERE expires_at < ?", (now,))
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO used_signatures (signature, expires_at) VALUES (?, ?)", (signature, expires_at)
            )
            return cursor.rowcount == 1
