"""Kalıcı kayıt: işlenen olaylar, bekleme kuyruğu ve kullanılmış imzalar.

Kayıt SQLite dosyasında durur. SQLite Python'un kendi kitaplığındadır.
Kayıt kişisel veri taşımaz. Olayın yalnız kimlik alanları saklanır.

Sunucu ve `replay-dead-letters` komutu ayrı süreçlerdir ve aynı dosyayı açar.
`exclusive()` bu süreçleri sıraya koyar. SQLite `BEGIN IMMEDIATE` ile dosyada
tek yazara izin verir. İkinci süreç ilk süreç bitene kadar bekler.
"""

from __future__ import annotations

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
"""

STATES = ("failed", "unknown")


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
    def __init__(self, path: str, *, clock: Callable[[], float] = time.time, busy_timeout: float = 60.0) -> None:
        """`busy_timeout`, başka sürecin kilidini beklemenin en uzun süresidir. Birim saniyedir."""
        self._clock = clock
        if path != ":memory:":
            # Dosyayı yalnız servisin kullanıcısı okuyabilsin.
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
            os.chmod(path, 0o600)
        # İşlem sınırlarını bu sınıf yönetir (`isolation_level=None`).
        self._db = sqlite3.connect(path, timeout=busy_timeout, isolation_level=None, check_same_thread=False)
        # Aynı bağlantıyı iki iş parçacığı kullanırsa işlemler karışmasın.
        self._thread_lock = threading.RLock()
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Kayıt dosyasında tek yazar olur. Öteki süreçler ve bağlantılar bekler.

        Blok hatayla biterse yazılar geri alınır. İç içe çağrı aynı işlemi kullanır.
        Bekleme `busy_timeout` süresini aşarsa `sqlite3.OperationalError` yükselir.
        """
        with self._thread_lock:
            if self._db.in_transaction:
                yield
                return
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def is_processed(self, event_id: str) -> bool:
        row = self._db.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)).fetchone()
        return row is not None

    def mark_processed(self, event_id: str, status: str) -> None:
        """Olayı işlenmiş sayar ve bekleme kuyruğundan çıkarır. İki yazı tek işlemdedir."""
        with self.exclusive():
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
        with self.exclusive():
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
        with self.exclusive():
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
        with self.exclusive():
            self._db.execute("DELETE FROM used_signatures WHERE expires_at < ?", (now,))
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO used_signatures (signature, expires_at) VALUES (?, ?)", (signature, expires_at)
            )
            return cursor.rowcount == 1
