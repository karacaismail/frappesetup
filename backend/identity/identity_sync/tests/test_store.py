"""Kalıcı kaydın testleri: işlenen olaylar ve bekleme kuyruğu."""

from __future__ import annotations

import os
import tempfile
import unittest

from identity_sync.events import Event
from identity_sync.store import Busy, Store

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

    def test_work_lock_blocks_a_second_connection(self) -> None:
        first = self.open()
        second = Store(self.path, lock_timeout=0.2)
        self.addCleanup(second.close)
        with first.work_lock():
            with self.assertRaises(Busy):
                with second.work_lock():
                    pass
        with second.work_lock():
            pass

    def test_work_lock_blocks_another_process(self) -> None:
        import subprocess
        import sys

        child = (
            "import sys\n"
            "from identity_sync.store import Busy, Store\n"
            "store = Store(sys.argv[1], lock_timeout=0.2)\n"
            "try:\n"
            "    with store.work_lock():\n"
            "        sys.exit(0)\n"
            "except Busy:\n"
            "    sys.exit(3)\n"
        )
        package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def run_child() -> int:
            return subprocess.run([sys.executable, "-c", child, self.path], cwd=package_root, timeout=30).returncode

        with self.open().work_lock():
            self.assertEqual(run_child(), 3)
        self.assertEqual(run_child(), 0)

    def test_records_written_under_the_work_lock_survive_an_interrupted_run(self) -> None:
        # Yeniden işleme yarıda kesilirse biten olayların kaydı kaybolmaz.
        store = self.open()
        with self.assertRaises(KeyboardInterrupt):
            with store.work_lock():
                store.mark_processed("e-1", "processed")
                store.add_dead_letter(EVENT, "x", state="unknown")
                raise KeyboardInterrupt
        store.close()

        reopened = self.open()
        self.assertTrue(reopened.is_processed("e-1"))
        self.assertEqual(reopened.dead_letters()[0].state, "unknown")

    def test_other_connection_can_write_records_while_work_lock_is_held(self) -> None:
        # İmza kaydı uzun süren bir işi beklemez.
        first, second = self.open(), Store(self.path, lock_timeout=0.2)
        self.addCleanup(second.close)
        with first.work_lock():
            self.assertTrue(second.claim_signature("abc", now=1.0, expires_at=301.0))
            self.assertEqual(second.dead_letters(), [])

    def test_approval_can_be_claimed_once(self) -> None:
        store = self.open()
        self.assertTrue(store.claim_approval("approval-1", "a" * 64, "replay_dead_letters"))
        # A second use is refused, with the same digest or with another one.
        self.assertFalse(store.claim_approval("approval-1", "a" * 64, "replay_dead_letters"))
        self.assertFalse(store.claim_approval("approval-1", "b" * 64, "invite_user"))
        store.close()
        self.assertFalse(self.open().claim_approval("approval-1", "a" * 64, "replay_dead_letters"))
        self.assertTrue(self.open().claim_approval("approval-2", "a" * 64, "replay_dead_letters"))

    def test_begin_keeps_an_accepted_event_without_counting_an_attempt(self) -> None:
        store = self.open()
        store.begin(EVENT)
        (letter,) = store.dead_letters()
        self.assertEqual((letter.state, letter.attempts), ("failed", 0))

        store.mark_writing(EVENT.id)
        self.assertEqual(store.dead_letters()[0].state, "unknown")

        store.add_dead_letter(EVENT, "x")
        self.assertEqual((store.dead_letters()[0].state, store.dead_letters()[0].attempts), ("failed", 1))

    def test_begin_does_not_reset_an_unknown_event(self) -> None:
        store = self.open()
        store.add_dead_letter(EVENT, "x", state="unknown")
        store.begin(EVENT)
        self.assertEqual((store.dead_letters()[0].state, store.dead_letters()[0].attempts), ("unknown", 1))

    def test_operation_journal_survives_a_crash_between_steps(self) -> None:
        steps = ["keycloak.create_user", "keycloak.add_organization_member", "keycloak.send_execute_actions_email"]
        store = self.open()
        store.operation_begin("onay-1", "invite_user", "o-1", steps)
        store.operation_step("onay-1", steps[0], "writing")
        store.operation_step("onay-1", steps[0], "done", subject="u-9")
        store.operation_step("onay-1", steps[1], "writing")
        store.close()  # the process dies here

        (operation,) = self.open().operations()
        self.assertEqual(operation["operation_id"], "onay-1")
        self.assertEqual(operation["subject"], "u-9")
        # A step that was started and never finished has an unknown outcome.
        self.assertEqual(operation["state"], "unknown")
        self.assertEqual([s["status"] for s in operation["steps"]], ["done", "unknown", "pending"])

    def test_finished_operation_is_not_listed(self) -> None:
        store = self.open()
        store.operation_begin("onay-1", "invite_user", "o-1", ["a"])
        store.operation_step("onay-1", "a", "writing")
        store.operation_step("onay-1", "a", "done")
        store.operation_finish("onay-1", "done")
        self.assertEqual(store.operations(), [])

    def test_failed_operation_is_listed_until_a_human_resolves_it(self) -> None:
        store = self.open()
        store.operation_begin("onay-1", "invite_user", "o-1", ["a", "b"])
        store.operation_step("onay-1", "a", "writing")
        store.operation_step("onay-1", "a", "failed")
        store.operation_finish("onay-1", "failed")
        self.assertEqual(store.operations()[0]["state"], "failed")

        self.assertTrue(store.operation_resolve("onay-1", "abandoned"))
        self.assertEqual(store.operations(), [])
        self.assertFalse(store.operation_resolve("onay-1", "abandoned"))
        self.assertFalse(store.operation_resolve("yok", "completed"))

    def test_operation_journal_stores_no_email(self) -> None:
        store = self.open()
        store.operation_begin("onay-1", "invite_user", "o-1", ["a"])
        self.assertNotIn("@", repr(store.operations()))

    def test_old_database_file_gets_the_state_column(self) -> None:
        import sqlite3

        old = sqlite3.connect(self.path)
        old.executescript(
            "CREATE TABLE dead_letters (event_id TEXT PRIMARY KEY, event TEXT NOT NULL, error TEXT NOT NULL,"
            " attempts INTEGER NOT NULL, first_failed_at REAL NOT NULL, last_failed_at REAL NOT NULL);"
        )
        old.execute(
            "INSERT INTO dead_letters VALUES (?, ?, 'eski', 1, 1.0, 1.0)",
            ("e-1", '{"id": "e-1", "kind": "user", "type": "REGISTER", "realm": "platform", "time": 1, "user_id": "u"}'),
        )
        old.commit()
        old.close()

        (letter,) = self.open().dead_letters()
        self.assertEqual((letter.error, letter.state), ("eski", "failed"))

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
