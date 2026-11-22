"""Persistent store tests: processed events and the pending queue."""

from __future__ import annotations

import os
import tempfile
import time
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
        store.add_dead_letter(EVENT, "tenant.provision tenant1: HTTP 503")
        store.close()

        (letter,) = self.open().dead_letters()
        self.assertEqual(letter.event, EVENT)
        self.assertEqual(letter.error, "tenant.provision tenant1: HTTP 503")
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
        # The expired record was deleted. The timestamp window already rejects this signature.
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
        # Completed event records survive an interrupted replay.
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
        # Recording a signature does not wait for a long-running operation.
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

    def test_progress_of_an_ordered_plan_survives_a_restart(self) -> None:
        store = self.open()
        store.begin(EVENT)
        self.assertEqual(store.progress(EVENT.id), frozenset())
        store.add_progress(EVENT.id, "a" * 64)
        store.add_progress(EVENT.id, "b" * 64)
        store.add_progress(EVENT.id, "a" * 64)  # the same step twice is one step
        store.add_dead_letter(EVENT, "x")  # a failure must not reset the progress
        store.close()

        self.assertEqual(self.open().progress(EVENT.id), frozenset({"a" * 64, "b" * 64}))
        self.assertEqual(self.open().progress("yok"), frozenset())

    def test_finished_operation_no_longer_names_the_user(self) -> None:
        # frappe-python-standartlari.md, G-15: the Keycloak id is personal data. It is kept only while needed.
        store = self.open()
        for operation_id, end in (("o-done", "done"), ("o-resolved", "resolved"), ("o-open", None)):
            store.operation_begin(operation_id, "invite_user", "org-1", ["s1"])
            store.operation_subject(operation_id, "u-1")
            if end == "done":
                store.operation_finish(operation_id, "done")
            elif end == "resolved":
                store.operation_finish(operation_id, "failed")
                store.operation_resolve(operation_id, "completed")

        self.assertEqual(self.subjects(store), {"o-done": "", "o-resolved": "", "o-open": "u-1"})

    def test_forgetting_a_subject_clears_every_operation_of_that_user(self) -> None:
        store = self.open()
        for operation_id, subject in (("o-1", "u-1"), ("o-2", "u-2")):
            store.operation_begin(operation_id, "invite_user", "org-1", ["s1"])
            store.operation_subject(operation_id, subject)

        store.forget_subject("u-1")

        self.assertEqual(self.subjects(store), {"o-1": "", "o-2": "u-2"})

    @staticmethod
    def subjects(store) -> dict[str, str]:
        return dict(store._db.execute("SELECT operation_id, subject FROM operations").fetchall())

    def test_account_job_is_listed_without_the_user_id(self) -> None:
        from identity_sync.events import Event

        store = self.open()
        job = Event(id="del-" + "0" * 40, kind="request", type="ACCOUNT_DELETION", realm="platform", time=1, user_id="u-1")
        store.add_dead_letter(job, "x")
        store.add_dead_letter(EVENT, "x")

        listed = {letter.event.id: letter.to_dict()["event"] for letter in store.dead_letters()}

        self.assertNotIn("user_id", listed[job.id])
        self.assertEqual(listed[EVENT.id].get("user_id"), EVENT.user_id)
        # The record itself keeps the id: the job needs it to continue.
        self.assertEqual({letter.event.user_id for letter in store.dead_letters()}, {"u-1", EVENT.user_id})

    def test_approval_and_operation_are_recorded_together(self) -> None:
        # A crash between "approval used" and "operation recorded" would lose the request.
        store = self.open()
        claimed = store.claim_approval("onay-1", "a" * 64, "invite_user", journal=("o-1", ["s1", "s2"]))

        self.assertTrue(claimed)
        (operation,) = store.operations()
        self.assertEqual((operation["operation_id"], [s["step"] for s in operation["steps"]]), ("onay-1", ["s1", "s2"]))
        # A second claim changes nothing.
        self.assertFalse(store.claim_approval("onay-1", "a" * 64, "invite_user", journal=("o-1", ["s1"])))
        self.assertEqual(len(store.operations()), 1)

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

        store = self.open()
        (letter,) = store.dead_letters()
        self.assertEqual((letter.error, letter.state), ("eski", "failed"))
        self.assertEqual(store.progress("e-1"), frozenset())

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


class RepeatClaimTest(unittest.TestCase):
    """Inceleme 18: the claim of a job repeat and the completion check are one database step."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "identity_sync.sqlite3")
        self.now = 100.0

    def open(self) -> Store:
        store = Store(self.path, clock=lambda: self.now)
        self.addCleanup(store.close)
        return store

    def test_claim_sees_a_job_another_connection_finished(self) -> None:
        first, second = self.open(), self.open()
        # The first connection read the job as unfinished. The second one finishes it meanwhile.
        self.assertFalse(first.is_processed("del-1"))
        second.mark_processed("del-1", "processed")

        self.assertEqual(first.claim_repeat("del-1", hold=10.0), "done")
        self.assertFalse(first.repeat_claimed("del-1"))

    def test_claim_is_exclusive_across_connections(self) -> None:
        first, second = self.open(), self.open()
        self.assertEqual(first.claim_repeat("del-1", hold=10.0), "claimed")
        self.assertEqual(second.claim_repeat("del-1", hold=10.0), "busy")
        self.now += 11.0  # the hold ran out, for example after a crash
        self.assertEqual(second.claim_repeat("del-1", hold=10.0), "claimed")

    def test_limits_refuse_a_claim_too_soon_or_too_often(self) -> None:
        store = self.open()
        self.assertEqual(store.claim_repeat("del-1", hold=1.0, max_attempts=2, min_interval=30.0), "claimed")
        store.release_repeat("del-1")
        self.assertEqual(store.claim_repeat("del-1", hold=1.0, max_attempts=2, min_interval=30.0), "limited")
        self.now += 30.0
        self.assertEqual(store.claim_repeat("del-1", hold=1.0, max_attempts=2, min_interval=30.0), "claimed")
        store.release_repeat("del-1")
        self.now += 30.0
        self.assertEqual(store.claim_repeat("del-1", hold=1.0, max_attempts=2, min_interval=30.0), "limited")

    def test_repeatable_jobs_reads_only_jobs_that_may_be_tried_now(self) -> None:
        store = self.open()
        for number in range(3000):
            store.add_dead_letter(Event(id=f"e-{number:04d}", kind="user", type="UPDATE_EMAIL", realm="platform",
                                        time=1, user_id=f"u-{number}"), "failed")
        jobs = [Event(id=f"del-{n}", kind="request", type="ACCOUNT_DELETION", realm="platform", time=1,
                      user_id=f"s-{n}") for n in range(5)]
        for job in jobs:
            store.add_dead_letter(job, "unknown", state="unknown")
        self.assertEqual(store.claim_repeat("del-0", hold=60.0), "claimed")  # busy now

        found = store.repeatable_jobs(limit=3, max_attempts=5, min_interval=30.0)

        self.assertEqual([letter.event.id for letter in found], ["del-1", "del-2", "del-3"])


class TwoLockDeadlineTest(unittest.TestCase):
    """Inceleme 20: the connection lock and the file lock together stay within one deadline."""

    def setUp(self) -> None:
        import sqlite3
        import threading

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "identity_sync.sqlite3")
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.release = threading.Event()
        file_held, connection_held = threading.Event(), threading.Event()

        def hold_file() -> None:
            # Another process holds the database file. EXCLUSIVE blocks readers too.
            other = sqlite3.connect(self.path, isolation_level=None)
            other.execute("BEGIN EXCLUSIVE")
            file_held.set()
            self.release.wait(10)
            other.execute("ROLLBACK")
            other.close()

        def hold_connection() -> None:
            # Another thread of this process uses the shared connection for a while.
            with self.store._db_lock:
                connection_held.set()
                time.sleep(0.25)

        threads = [threading.Thread(target=hold_file), threading.Thread(target=hold_connection)]
        for thread in threads:
            thread.start()
            self.addCleanup(thread.join, 10)
        # Cleanups run last in, first out: the file is released before the threads are joined.
        self.addCleanup(self.release.set)
        self.assertTrue(file_held.wait(5) and connection_held.wait(5))

    def assert_within(self, call, limit: float = 0.4) -> None:
        from identity_sync.deadline import deadline

        started = time.monotonic()
        with deadline(limit, grace=0.0), self.assertRaises(Busy):
            call()
        self.assertLess(time.monotonic() - started, limit + 0.08)

    def test_a_write_before_a_target_call(self) -> None:
        self.assert_within(lambda: self.store.begin(EVENT))

    def test_an_outcome_record(self) -> None:
        self.assert_within(lambda: self.store.add_dead_letter(EVENT, "failed"))

    def test_the_queue_query(self) -> None:
        self.assert_within(lambda: self.store.repeatable_jobs(limit=3, max_attempts=5, min_interval=30.0))
