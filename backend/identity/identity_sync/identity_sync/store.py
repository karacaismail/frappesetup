"""Kalıcı kayıt: işlenen olaylar ve bekleme kuyruğu.

Kayıt SQLite dosyasında durur. SQLite Python'un kendi kitaplığındadır.
Kayıt kişisel veri taşımaz. Olayın yalnız kimlik alanları saklanır.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable
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
    attempts INTEGER NOT NULL,
    first_failed_at REAL NOT NULL,
    last_failed_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class DeadLetter:
    event: Event
    error: str
    attempts: int
    first_failed_at: float
    last_failed_at: float

    def to_dict(self) -> dict[str, object]:
        return {
            "event": self.event.to_dict(),
            "error": self.error,
            "attempts": self.attempts,
            "first_failed_at": self.first_failed_at,
            "last_failed_at": self.last_failed_at,
        }


class Store:
    def __init__(self, path: str, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        if path != ":memory:":
            # Dosyayı yalnız servisin kullanıcısı okuyabilsin.
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
            os.chmod(path, 0o600)
        # Sunucu tek iş parçacığıyla çalışır. Testler bağlantıyı başka iş parçacığından kapatır.
        self._db = sqlite3.connect(path, check_same_thread=False)
        with self._db:
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def is_processed(self, event_id: str) -> bool:
        row = self._db.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)).fetchone()
        return row is not None

    def mark_processed(self, event_id: str, status: str) -> None:
        """Olayı işlenmiş sayar ve bekleme kuyruğundan çıkarır. İki yazı tek işlemdedir."""
        with self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO processed_events (event_id, status, processed_at) VALUES (?, ?, ?)",
                (event_id, status, self._clock()),
            )
            self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (event_id,))

    def add_dead_letter(self, event: Event, error: str) -> None:
        """Olayı bekleme kuyruğuna yazar. Olay zaten kuyruktaysa deneme sayısını artırır."""
        now = self._clock()
        with self._db:
            self._db.execute(
                """
                INSERT INTO dead_letters (event_id, event, error, attempts, first_failed_at, last_failed_at)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    error = excluded.error,
                    attempts = attempts + 1,
                    last_failed_at = excluded.last_failed_at
                """,
                (event.id, json.dumps(event.to_dict()), error, now, now),
            )

    def remove_dead_letter(self, event_id: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM dead_letters WHERE event_id = ?", (event_id,))

    def dead_letters(self) -> list[DeadLetter]:
        rows = self._db.execute(
            "SELECT event, error, attempts, first_failed_at, last_failed_at FROM dead_letters "
            "ORDER BY first_failed_at, event_id"
        ).fetchall()
        return [
            DeadLetter(
                event=Event(**json.loads(event)),
                error=error,
                attempts=attempts,
                first_failed_at=first,
                last_failed_at=last,
            )
            for event, error, attempts, first, last in rows
        ]
