"""H-5: an account deletion whose step timed out settles by itself.

The final MVP test saw this: the tenant call of step 4 timed out after 10 seconds. The job stayed
`unknown`. The tenant finished the work 2 seconds later. The Keycloak user was never deleted.

Expected behaviour (docs/sozlesmeler.md, section 7, and contracts/identity_sync.openapi.yaml):

1. Every step of the deletion job can be repeated. A repeated `anonymize_user` call gets the same
   reply for the same identity. So the service repeats the step. It never guesses from a list.
2. The step is done only when the reply says so (`anonymized` true, both fields booleans).
   A reply with a missing field or a wrong type keeps the job `unknown`.
3. The repeat runs on the next deletion request for the account, or while the next event is
   handled. An event settles at most 3 jobs and spends at most 5 seconds on them. The work lock
   is not held while a target is called. Repeats of one job are limited in number and spacing,
   and two repeats of one job never run at the same time.
4. A deletion request answers within the anonymize timeout, plus the wait for the work lock.

The fake targets answer later than the timeout. The real case was 12 seconds against 10. The tests
keep the same order with shorter times, so the run stays short.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from unittest import mock

from identity_sync import pipeline
from identity_sync.events import Event
from identity_sync.httpjson import TransportError, deadline
from identity_sync.store import Store

from . import fakes
from .fakes import ORG_ID, SUBJECT, keycloak_user
from .test_server import PRESS_TOKEN, ServerCase

TIMEOUT = 0.3
LATE = 0.6
OTHER_SUBJECT = "33333333-3333-4333-8333-333333333333"
OTHER_EVENT = {"id": "e-other", "kind": "user", "type": "UPDATE_EMAIL", "realm": "platform", "time": 2,
               "user_id": OTHER_SUBJECT}


class UnknownDeletionCase(ServerCase):
    stack_settings = {"anonymize_timeout": TIMEOUT}

    def setUp(self) -> None:
        super().setUp()
        self.seed(SUBJECT)
        self.job_id = self.job_of(SUBJECT)
        self.finished = threading.Event()
        # The tests start with no spacing between repeats and a claim that lasts only the timeout.
        # Some tests check the spacing and the longer claim themselves.
        for name, value in (("SETTLE_INTERVAL_SECONDS", 0.0), ("REPEAT_HOLD_MARGIN_SECONDS", 0.0)):
            patcher = mock.patch.object(pipeline, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def seed(self, subject: str) -> None:
        """A sample account on Keycloak, Press and the tenant. ServerCase already added SUBJECT to Keycloak."""
        issuer = self.stack.issuer
        email = "ayse@example.test" if subject == SUBJECT else f"ornek-{subject[:8]}@example.test"
        if subject != SUBJECT:
            self.stack.keycloak.add_user(keycloak_user(subject=subject, email=email), [])
        self.stack.press.seed_member(issuer, subject, email, ORG_ID)
        self.stack.tenant.seed_user(issuer, subject, email)

    def job_of(self, subject: str) -> str:
        return self.stack.app.processor.account_job(subject, time=0).id

    def slow(self, site: fakes.FakeSite, path: str, delay: float, *, reply: fakes.Reply | None = None,
             times: int | None = None) -> None:
        """The target does the work, then answers after `delay`. Only the first `times` calls are slow."""
        work = site._defaults[("POST", path)]
        calls = {"count": 0}

        def late(req: fakes.Recorded) -> fakes.Reply:
            calls["count"] += 1
            if times is None or calls["count"] <= times:
                time.sleep(delay)
            answer = work(req) if reply is None else reply
            self.finished.set()
            return answer

        site.on("POST", path, late)

    def press_request(self, subject: str = SUBJECT) -> dict:
        body = {"issuer": self.stack.issuer, "subject": subject, "reauthenticated_at": int(self.now) - 10}
        status, reply = self.post_json("/v1/account-deletions", body, PRESS_TOKEN)
        self.assertEqual(status, 200)
        return reply

    def first_request_times_out(self, subject: str = SUBJECT) -> None:
        self.finished.clear()
        reply = self.press_request(subject)
        self.assertEqual(reply["status"], "unknown")
        self.assertIn(subject, self.stack.keycloak.users)
        self.assertTrue(self.finished.wait(5))

    def tenant_anonymize_calls(self) -> int:
        return len(self.stack.tenant.calls("POST", fakes.TENANT_ANONYMIZE))

    def done(self, job_id: str) -> bool:
        return self.stack.app.store.is_processed(job_id)


class RepeatTest(UnknownDeletionCase):
    def test_next_request_repeats_the_timed_out_tenant_step(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()

        reply = self.press_request()

        self.assertEqual(reply["status"], "processed")
        self.assertEqual(reply["actions"], ["tenant.anonymize_user", "keycloak.delete_user"])
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        # The step was repeated once. The identity list was not used to decide.
        self.assertEqual(self.tenant_anonymize_calls(), 2)
        self.assertEqual(len(self.stack.tenant.calls("GET", fakes.TENANT_LIST)), 0)
        self.assertTrue(self.done(self.job_id))

    def test_timed_out_press_step_is_repeated_the_same_way(self) -> None:
        press = self.stack.press
        self.slow(press, fakes.PRESS_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()

        reply = self.press_request()

        self.assertEqual(reply["status"], "processed")
        self.assertEqual(reply["actions"], ["press.anonymize_user", "tenant.anonymize_user", "keycloak.delete_user"])
        self.assertEqual(len(press.calls("POST", fakes.PRESS_ANONYMIZE)), 2)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)

    def test_incomplete_or_mistyped_reply_keeps_the_job_unknown(self) -> None:
        cases = {
            "missing found": {"message": {"anonymized": True}},
            "text instead of boolean": {"message": {"anonymized": "true", "found": True}},
            "tenant body without the fields": {"message": {"user": "deleted-user-0@deleted.invalid",
                                                           "enabled": False, "status": "Anonymized"}},
            "not anonymized": {"message": {"anonymized": False, "found": True}},
        }
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()
        for name, body in cases.items():
            with self.subTest(reply=name):
                self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (200, body))

                reply = self.press_request()

                self.assertEqual(reply["status"], "unknown")
                self.assertIn(SUBJECT, self.stack.keycloak.users)
                self.assertEqual(self.stack.app.store.dead_letter_state(self.job_id), "unknown")

    def test_next_event_repeats_the_timed_out_step(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()

        status, _reply = self.post_event(OTHER_EVENT)

        self.assertEqual(status, 202)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.tenant_anonymize_calls(), 2)
        self.assertTrue(self.done(self.job_id))

    def test_failed_repeat_on_an_event_keeps_the_job_queued(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (500, None))

        status, _reply = self.post_event(OTHER_EVENT)

        self.assertEqual(status, 202)
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertIsNotNone(self.stack.app.store.dead_letter_state(self.job_id))
        self.assertFalse(self.done(self.job_id))


class LimitTest(UnknownDeletionCase):
    def test_repeats_of_one_job_are_spaced_and_counted(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()
        # A permanent error: the pipeline does not retry it within one attempt.
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (400, None))

        with mock.patch.object(pipeline, "SETTLE_INTERVAL_SECONDS", 60.0):
            for number in range(3):
                self.post_event({**OTHER_EVENT, "id": f"e-other-{number}"})

        # The timed-out request was attempt 1. The events came too soon after it and called nothing.
        self.assertEqual(self.tenant_anonymize_calls(), 1)

        with mock.patch.object(pipeline, "SETTLE_MAX_ATTEMPTS", 3):
            for number in range(4):
                self.post_event({**OTHER_EVENT, "id": f"e-more-{number}"})

        # Attempts 2 and 3 repeated the step. Attempt 3 was the last one allowed. A human decides after that.
        self.assertEqual(self.tenant_anonymize_calls(), 3)
        self.assertIn(SUBJECT, self.stack.keycloak.users)

    def test_one_event_settles_at_most_three_jobs_within_its_budget(self) -> None:
        subjects = [f"4444444{n}-4444-4444-8444-444444444444" for n in range(5)]
        for subject in subjects:
            self.seed(subject)
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=len(subjects))
        for subject in subjects:
            self.first_request_times_out(subject)
        # Every repeat is slow now: each takes 2 seconds.
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, 2.0)
        before = self.tenant_anonymize_calls()

        with mock.patch.object(pipeline, "SETTLE_BUDGET_SECONDS", 1.0):
            started = time.monotonic()
            status, _reply = self.post_event(OTHER_EVENT)
            spent = time.monotonic() - started

        self.assertEqual(status, 202)
        self.assertLess(spent, 1.0 + 1.0)
        self.assertLessEqual(self.tenant_anonymize_calls() - before, pipeline.SETTLE_MAX_JOBS)
        self.assertEqual(pipeline.SETTLE_MAX_JOBS, 3)
        self.assertEqual(pipeline.SETTLE_BUDGET_SECONDS, 5.0)


class ConcurrencyTest(UnknownDeletionCase):
    """The repeat waits on a gate that the test opens. The timeout is long, so nothing is cut short."""

    stack_settings = {"anonymize_timeout": 10.0}

    def setUp(self) -> None:
        super().setUp()
        tenant = self.stack.tenant
        # The first answer has no definite result, so the job is `unknown` at once.
        tenant.on("POST", fakes.TENANT_ANONYMIZE, (200, {"message": {}}))
        self.assertEqual(self.press_request()["status"], "unknown")
        # The fake tenant has answered, so no call is open. End the claim the unknown outcome kept.
        self.stack.app.store.release_repeat(self.job_id)
        self.gate, self.waiting = threading.Event(), threading.Event()
        work = tenant._defaults[("POST", fakes.TENANT_ANONYMIZE)]

        def gated(req: fakes.Recorded) -> fakes.Reply:
            self.waiting.set()
            self.gate.wait(10)
            return work(req)

        tenant.on("POST", fakes.TENANT_ANONYMIZE, gated)
        self.addCleanup(self.gate.set)
        self.event_thread = threading.Thread(target=self.post_event, args=(OTHER_EVENT,))

    def start_repeat(self) -> None:
        self.event_thread.start()
        self.addCleanup(self.event_thread.join, 10)
        self.assertTrue(self.waiting.wait(5))  # the event repeats the step and waits for the tenant

    def test_work_lock_is_free_while_a_target_is_called(self) -> None:
        # Another process, for example the replay command, must not wait for the tenant.
        self.start_repeat()

        started = time.monotonic()
        with self.stack.app.store.work_lock():
            waited = time.monotonic() - started

        self.assertLess(waited, 0.5)

    def test_two_repeats_of_one_job_never_run_at_the_same_time(self) -> None:
        before = self.tenant_anonymize_calls()
        self.start_repeat()

        # The HTTP server handles one request at a time. A second caller is another process, for
        # example the replay command. It runs the same job through the processor directly.
        processor = self.stack.app.processor
        result = processor.handle(processor.account_job(SUBJECT, time=1))
        self.gate.set()
        self.event_thread.join(10)

        # The second caller found the job busy and called nothing.
        self.assertEqual(result.status, "unknown")
        self.assertEqual(self.tenant_anonymize_calls() - before, 1)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        self.assertTrue(self.done(self.job_id))


class DeadlineTest(UnknownDeletionCase):
    def test_deletion_request_answers_within_the_anonymize_timeout(self) -> None:
        # Press and the tenant each take a little less than the timeout. Together they take longer.
        self.slow(self.stack.press, fakes.PRESS_ANONYMIZE, TIMEOUT * 0.8, times=1)
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, TIMEOUT * 0.8, times=1)

        started = time.monotonic()
        reply = self.press_request()
        spent = time.monotonic() - started

        # The work lock was free, so the reply came within the timeout plus the retry pauses.
        self.assertLess(spent, TIMEOUT + 1.0)
        self.assertIn(reply["status"], ("unknown", "dead_lettered"))
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        # The next event finishes the job.
        self.post_event(OTHER_EVENT)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        self.assertTrue(self.done(self.job_id))


class NotFoundTest(UnknownDeletionCase):
    def test_404_from_the_tenant_anonymize_call_keeps_the_job_unknown(self) -> None:
        # O-43: only 200 with both fields is a result. An old tenant may answer 404 after it removed
        # the link while the anonymization is still unfinished.
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, fakes.frappe_error(404, "IdentityNotFound"))

        reply = self.press_request()

        self.assertEqual(reply["status"], "unknown")
        self.assertEqual(self.stack.app.store.dead_letter_state(self.job_id), "unknown")
        deletes = [r for r in self.stack.keycloak.requests if r.method == "DELETE" and r.path.endswith(f"/users/{SUBJECT}")]
        self.assertEqual(deletes, [])
        self.assertIn(SUBJECT, self.stack.keycloak.users)

    def test_unknown_identity_is_200_with_found_false(self) -> None:
        # The tenant has no link for this account: 200 with `found` false finishes the step.
        self.stack.tenant.links.clear()

        reply = self.press_request()

        self.assertEqual(reply["status"], "processed")
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)


class OpenTargetCallTest(UnknownDeletionCase):
    def test_second_press_request_does_not_call_while_the_first_call_may_still_run(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        with mock.patch.object(pipeline, "REPEAT_HOLD_MARGIN_SECONDS", 30.0):
            self.assertEqual(self.press_request()["status"], "unknown")
            # The tenant still works on the first call. A new request must not send a second one.
            reply = self.press_request()

        self.assertEqual(reply["status"], "unknown")
        self.assertEqual(self.tenant_anonymize_calls(), 1)
        self.assertIn(SUBJECT, self.stack.keycloak.users)

    def test_press_path_keeps_the_attempt_and_spacing_limits(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()
        # From now on the tenant answers without a result.
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (200, {"message": {}}))

        with mock.patch.object(pipeline, "SETTLE_INTERVAL_SECONDS", 60.0):
            self.assertEqual(self.press_request()["status"], "unknown")
        self.assertEqual(self.tenant_anonymize_calls(), 1)  # too soon: nothing was sent

        with mock.patch.object(pipeline, "SETTLE_MAX_ATTEMPTS", 2):
            self.press_request()
            self.press_request()
        self.assertEqual(self.tenant_anonymize_calls(), 2)  # attempt 2 was the last one


class BudgetTest(UnknownDeletionCase):
    def test_a_reply_sent_in_small_pieces_cannot_stretch_the_event_budget(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()
        # Each piece comes before the per-read timeout, but the whole body takes about 5 seconds.
        body = fakes.Trickle({"message": {"anonymized": True, "found": True}}, piece=2, pause=0.2)
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (200, body))

        with mock.patch.object(pipeline, "SETTLE_BUDGET_SECONDS", 1.0):
            started = time.monotonic()
            status, _reply = self.post_event(OTHER_EVENT)
            spent = time.monotonic() - started

        self.assertEqual(status, 202)
        self.assertLess(spent, 1.0 + 1.0)
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertFalse(self.done(self.job_id))

    def test_a_large_queue_is_not_read_in_full(self) -> None:
        self.slow(self.stack.tenant, fakes.TENANT_ANONYMIZE, LATE, times=1)
        self.first_request_times_out()
        store = self.stack.app.store
        for number in range(3000):
            store.add_dead_letter(
                Event(id=f"e-big-{number:04d}", kind="user", type="UPDATE_EMAIL", realm="platform", time=1,
                      user_id=f"u-{number}"),
                "failed",
            )
        full_reads = []
        read = store.dead_letters

        def counted(**kwargs):
            if kwargs.get("limit") is None:
                full_reads.append(kwargs)
            return read(**kwargs)

        with mock.patch.object(store, "dead_letters", counted):
            started = time.monotonic()
            self.post_event(OTHER_EVENT)
            spent = time.monotonic() - started

        self.assertEqual(full_reads, [])
        self.assertLess(spent, 2.0)
        self.assertTrue(self.done(self.job_id))

    def test_deletion_request_does_not_wait_for_the_work_lock_past_its_deadline(self) -> None:
        store = self.stack.app.store
        held, release = threading.Event(), threading.Event()

        def hold() -> None:
            with store.work_lock():
                held.set()
                release.wait(10)

        thread = threading.Thread(target=hold)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(held.wait(5))

        body = {"issuer": self.stack.issuer, "subject": SUBJECT, "reauthenticated_at": int(self.now) - 10}
        started = time.monotonic()
        status, reply = self.post_json("/v1/account-deletions", body, PRESS_TOKEN)
        spent = time.monotonic() - started

        self.assertEqual((status, reply), (503, {"error": "busy"}))
        self.assertLess(spent, TIMEOUT + 1.0)

    def test_retry_pauses_stop_at_the_deadline(self) -> None:
        processor = self.stack.app.processor
        self.stack.sleeps.clear()

        def fail() -> None:
            raise TransportError("network error")

        with deadline(0.05), self.assertRaises(pipeline._Failed):
            processor._retry("tenant.anonymize_user tenant1", fail)

        self.assertEqual(self.stack.sleeps, [])


class FinishedMeanwhileTest(UnknownDeletionCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db_path = os.path.join(folder.name, "identity_sync.sqlite3")
        self.stack_settings = {**self.stack_settings, "db_path": self.db_path}
        super().setUp()

    def test_a_job_finished_by_another_connection_is_not_run_again(self) -> None:
        # Two connections to one database file. The second one finishes the job while the first
        # still reads it as unfinished.
        path = self.db_path
        other = Store(path)
        self.addCleanup(other.close)
        processor = self.stack.app.processor
        job = processor.account_job(SUBJECT, time=1)
        other.mark_processed(job.id, "processed")
        writes = len(self.downstream_writes())

        with mock.patch.object(self.stack.app.store, "is_processed", return_value=False):
            with self.stack.app.store.work_lock():
                result = processor._handle_job(job, False, None)

        self.assertEqual(result.status, "duplicate")
        self.assertEqual(len(self.downstream_writes()), writes)
        self.assertIn(SUBJECT, self.stack.keycloak.users)
