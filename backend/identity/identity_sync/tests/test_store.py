"""Kalıcı kaydın testleri: işlenen olaylar ve bekleme kuyruğu."""

from __future__ import annotations

import os
import tempfile
import unittest

from identity_sync.events import Event
from identity_sync.store import Store

EVENT = Event(id="e-1", kind="admin", type="ORGANIZATION_MEMBERSHIP_DELETE", realm="platform", time=7, user_id="u-1", organization_id="o-1")


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "identity_sync.sqlite3")

    def open(self, clock=lambda: 100.0) -> Store:
        store = Store(self.path, clock=clock)
        self.addCleanup(store.close)
        return store

    def test_processed_event_survives_restart(self) -> None:
        first = self.open()
        self.assertFalse(first.is_processed("e-1"))
        first.mark_processed("e-1", "processed")
        first.close()

        self.assertTrue(self.open().is_processed("e-1"))

    def test_mark_processed_twice_is_fine(self) -> None:
        store = self.open()
        store.mark_processed("e-1", "processed")
        store.mark_processed("e-1", "processed")
        self.assertTrue(store.is_processed("e-1"))

    def test_dead_letter_round_trip(self) -> None:
        store = self.open()
        store.add_dead_letter(EVENT, "tenant.provision kiraci1: HTTP 503")
        store.close()

        (letter,) = self.open().dead_letters()
        self.assertEqual(letter.event, EVENT)
        self.assertEqual(letter.error, "tenant.provision kiraci1: HTTP 503")
        self.assertEqual((letter.attempts, letter.first_failed_at, letter.last_failed_at), (1, 100.0, 100.0))

    def test_second_failure_counts_attempt_and_keeps_first_time(self) -> None:
        self.open(clock=lambda: 100.0).add_dead_letter(EVENT, "ilk")
        later = self.open(clock=lambda: 250.0)
        later.add_dead_letter(EVENT, "ikinci")

        (letter,) = later.dead_letters()
        self.assertEqual((letter.attempts, letter.error), (2, "ikinci"))
        self.assertEqual((letter.first_failed_at, letter.last_failed_at), (100.0, 250.0))

    def test_remove_dead_letter(self) -> None:
        store = self.open()
        store.add_dead_letter(EVENT, "x")
        store.remove_dead_letter("e-1")
        self.assertEqual(store.dead_letters(), [])

    def test_dead_letters_come_oldest_first(self) -> None:
        times = iter([300.0, 100.0])
        store = self.open(clock=lambda: next(times))
        store.add_dead_letter(Event(id="yeni", kind="user", type="REGISTER", realm="platform", time=1, user_id="u"), "x")
        store.add_dead_letter(Event(id="eski", kind="user", type="REGISTER", realm="platform", time=1, user_id="u"), "x")
        self.assertEqual([letter.event.id for letter in store.dead_letters()], ["eski", "yeni"])

    @unittest.skipIf(os.name == "nt", "POSIX dosya izinleri")
    def test_database_file_is_private(self) -> None:
        self.open()
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
