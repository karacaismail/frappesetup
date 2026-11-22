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

    def test_dead_letter_state_defaults_to_failed_and_can_be_unknown(self) -> None:
        store = self.open()
        store.add_dead_letter(EVENT, "x")
        self.assertEqual(store.dead_letters()[0].state, "failed")
        store.add_dead_letter(EVENT, "y", state="unknown")
        self.assertEqual(store.dead_letters()[0].state, "unknown")

    def test_signature_can_be_claimed_once(self) -> None:
        store = self.open()
        self.assertTrue(store.claim_signature("abc", now=1000.0, expires_at=1300.0))
        self.assertFalse(store.claim_signature("abc", now=1000.0, expires_at=1300.0))
        store.close()
        self.assertFalse(self.open().claim_signature("abc", now=1001.0, expires_at=1301.0))

    def test_expired_signatures_are_removed(self) -> None:
        store = self.open()
        store.claim_signature("abc", now=1000.0, expires_at=1300.0)
        self.assertTrue(store.claim_signature("def", now=1301.0, expires_at=1601.0))
        # Süresi dolan kayıt silindi. Zaman penceresi bu imzayı artık zaten reddeder.
        self.assertTrue(store.claim_signature("abc", now=1301.0, expires_at=1601.0))

    def test_exclusive_blocks_a_second_connection(self) -> None:
        import sqlite3

        first = self.open()
        second = Store(self.path, busy_timeout=0.2)
        self.addCleanup(second.close)
        with first.exclusive():
            first.mark_processed("e-1", "processed")
            with self.assertRaises(sqlite3.OperationalError):
                with second.exclusive():
                    pass
        with second.exclusive():
            self.assertTrue(second.is_processed("e-1"))

    def test_exclusive_rolls_back_on_error(self) -> None:
        store = self.open()
        with self.assertRaises(RuntimeError):
            with store.exclusive():
                store.mark_processed("e-1", "processed")
                raise RuntimeError("boom")
        self.assertFalse(store.is_processed("e-1"))

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
