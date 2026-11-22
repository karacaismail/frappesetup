"""Every path of the account deletion flow, one test per row of the table in README.md
("Hesap silme yolları"). The rows come from docs/sozlesmeler.md, section 7.

Each test checks four things together:

1. what Keycloak answered when it was read,
2. which write requests left the service,
3. what the record says afterwards (finished records and the queue),
4. that no reply shows the raw Keycloak id of the account.

All requests go through the real HTTP entry of the service.
"""

from __future__ import annotations

import json
import sqlite3

from . import fakes
from .fakes import ORG_ID, SUBJECT, keycloak_user
from .test_server import NOW, PRESS_TOKEN, PREVIEW_TOKEN, ServerCase

CLOSE = ["press.remove_team_member", "tenant.set_enabled", "tenant.revoke_user_installations"]
ANONYMIZE = ["press.anonymize_user", "tenant.anonymize_user"]
FULL = ["keycloak.disable_user", *CLOSE, *ANONYMIZE, "keycloak.delete_user"]
DELETE_EVENT = {"id": "e-del", "kind": "admin", "type": "USER_DELETE", "realm": "platform", "time": 1, "user_id": SUBJECT}


class DeletionPathsTest(ServerCase):
    def setUp(self) -> None:
        super().setUp()
        issuer = self.stack.issuer
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID, api_keys=1)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        self.store = self.stack.app.store
        self.job_id = self.stack.app.processor.account_job(SUBJECT, time=0).id
        self.replies: list[object] = []

    # --- the four observations ---

    def keycloak_answers(self, *answers: str) -> None:
        """Answer the user reads in order: "open", "closed", "gone" or "error". The last one repeats."""
        keycloak = self.stack.keycloak
        left = list(answers)

        def read(_req: fakes.Recorded) -> fakes.Reply:
            answer = left.pop(0) if len(left) > 1 else left[0]
            if answer == "error":
                return 500, None
            if answer == "gone":
                return 404, {"error": "User not found"}
            return 200, keycloak_user(enabled=answer == "open")

        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", read)

    def writes(self) -> int:
        return len(self.downstream_writes() + self.keycloak_writes())

    def anonymized(self) -> int:
        return len(self.stack.press.calls("POST", fakes.PRESS_ANONYMIZE)) + len(
            self.stack.tenant.calls("POST", fakes.TENANT_ANONYMIZE)
        )

    def record(self) -> dict[str, object]:
        return {
            "job_done": self.store.is_processed(self.job_id),
            "event_done": self.store.is_processed("e-del"),
            "queue": [letter.event.id for letter in self.store.dead_letters()],
        }

    def seen(self, reply: tuple[int, object]) -> object:
        self.replies.append(reply[1])
        return reply[1]

    def tearDown(self) -> None:
        # 4: whatever the path, no reply named the account.
        self.assertGreater(len(self.replies), 0)
        self.assertNotIn(SUBJECT, json.dumps(self.replies))
        super().tearDown()

    # --- entries ---

    def press_request(self) -> dict:
        body = {"issuer": self.stack.issuer, "subject": SUBJECT, "reauthenticated_at": NOW - 10}
        return self.seen(self.post_json("/v1/account-deletions", body, PRESS_TOKEN))

    def delete_event(self, event_id: str = "e-del") -> dict:
        return self.seen(self.post_event({**DELETE_EVENT, "id": event_id}))

    def queue_listing(self) -> dict:
        return self.seen(self.call("GET", "/v1/dead-letters", None, self.bearer(PREVIEW_TOKEN)))

    def replay_preview(self) -> dict:
        return self.seen(self.post_json("/v1/dead-letters/replay", {"dry_run": True}, PREVIEW_TOKEN))

    def replay(self, preview: dict, approval: str = "onay-p1") -> tuple[int, dict]:
        body = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": approval}
        status, reply = self.post_json("/v1/dead-letters/replay", body)
        return status, self.seen((status, reply))

    def steps(self, preview: dict) -> list[str]:
        return [p["operation"] for result in preview["results"] for p in result.get("previews", [])]

    # --- rows 1 to 3: the Press request ---

    def test_row_01_press_request_runs_all_five_steps(self) -> None:
        reply = self.press_request()

        self.assertEqual((reply["status"], reply["actions"], reply["request_id"]), ("processed", FULL, self.job_id))
        self.assertEqual(self.anonymized(), 2)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    def test_row_02_failed_step_stops_and_queues_the_job(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (503, None))

        reply = self.press_request()

        self.assertEqual((reply["status"], reply["request_id"]), ("dead_lettered", self.job_id))
        # Steps 1 to 3 ran once each. Step 4 stopped at Press, so the tenant was not asked to anonymize.
        self.assertEqual(len(self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)), 1)
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)), 1)
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_ANONYMIZE)), 0)
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.record(), {"job_done": False, "event_done": False, "queue": [self.job_id]})
        self.queue_listing()

    def test_row_03_second_press_request_writes_nothing(self) -> None:
        self.press_request()
        before = self.writes()

        reply = self.press_request()

        self.assertEqual((reply["status"], reply["actions"]), ("duplicate", []))
        self.assertEqual(self.writes(), before)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    # --- rows 4 to 8: the Keycloak delete event ---

    def test_row_04_event_after_a_finished_job_writes_nothing(self) -> None:
        self.press_request()  # step 5 deleted the user; Keycloak now reports that delete
        before = self.writes()

        reply = self.delete_event()

        self.assertEqual(reply["status"], "duplicate")
        self.assertEqual(self.writes(), before)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    def test_row_05_event_for_a_gone_user_runs_steps_two_to_four(self) -> None:
        self.keycloak_answers("gone")

        reply = self.delete_event()

        self.assertEqual((reply["status"], reply["actions"]), ("processed", [*CLOSE, *ANONYMIZE]))
        self.assertEqual(self.keycloak_writes(), [])
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    def test_row_06_event_continues_the_job_the_press_request_left(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        self.press_request()
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, fakes.DONE)
        self.keycloak_answers("gone")
        before = self.writes()

        reply = self.delete_event()

        self.assertEqual((reply["status"], reply["actions"]), ("processed", ["tenant.anonymize_user"]))
        self.assertEqual(self.writes(), before + 1)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    def test_row_07_event_with_a_failed_read_waits_and_writes_nothing(self) -> None:
        self.keycloak_answers("error", "error", "error", "gone")  # a later read would work

        reply = self.delete_event()

        self.assertEqual((reply["status"], reply["actions"]), ("dead_lettered", []))
        self.assertEqual(self.writes(), 0)
        self.assertEqual(self.record(), {"job_done": False, "event_done": False, "queue": ["e-del"]})
        self.queue_listing()

    def test_row_08_event_for_a_user_keycloak_still_has_only_closes(self) -> None:
        for answer in ("closed", "open"):
            with self.subTest(answer=answer):
                self.keycloak_answers(answer)
                reply = self.delete_event(f"e-{answer}")
                self.assertEqual(reply["status"], "processed")
                self.assertEqual(self.anonymized(), 0)
                self.assertFalse(self.store.is_processed(self.job_id))
                self.assertTrue(self.store.is_processed(f"e-{answer}"))

    # --- rows 9 to 12: what a preview and the queue show ---

    def queue_the_delete_event(self) -> None:
        self.keycloak_answers("error")
        self.delete_event()

    def test_row_09_preview_of_a_queued_event_when_the_user_is_gone(self) -> None:
        self.queue_the_delete_event()
        self.keycloak_answers("gone")

        preview = self.replay_preview()

        self.assertEqual(self.steps(preview), [*CLOSE, *ANONYMIZE])
        self.assertIn(self.job_id, json.dumps(preview))
        self.assertEqual((self.writes(), self.record()["queue"]), (0, ["e-del"]))

    def test_row_10_preview_of_a_queued_event_when_the_user_is_closed(self) -> None:
        # The account still exists, closed. The plan is the event's own plan, yet the preview
        # of a delete event never names the account.
        self.queue_the_delete_event()
        self.keycloak_answers("closed")

        preview = self.replay_preview()

        self.assertEqual(self.steps(preview), CLOSE)
        self.assertIn(self.job_id, json.dumps(preview))
        self.assertEqual((self.writes(), self.record()["queue"]), (0, ["e-del"]))

    def test_row_11_preview_of_a_queued_event_when_the_read_fails(self) -> None:
        self.queue_the_delete_event()

        preview = self.replay_preview()

        self.assertEqual((preview["results"][0]["status"], self.steps(preview)), ("failed", []))
        self.assertEqual((self.writes(), self.record()["queue"]), (0, ["e-del"]))

    def test_row_12_queue_listing_hides_the_account_of_a_delete_event(self) -> None:
        self.queue_the_delete_event()

        listing = self.queue_listing()

        (letter,) = listing["dead_letters"]
        self.assertEqual((letter["event"]["id"], letter["event"]["type"]), ("e-del", "USER_DELETE"))
        self.assertNotIn("user_id", letter["event"])

    # --- rows 13 to 16: the approved replay ---

    def test_row_13_approved_close_plan_stays_the_events_plan(self) -> None:
        self.queue_the_delete_event()
        self.keycloak_answers("closed")
        preview = self.replay_preview()
        # Check at execution: 2 reads. Every later read says the user is gone.
        self.keycloak_answers("closed", "closed", "gone")

        status, reply = self.replay(preview)

        self.assertEqual((status, reply["results"][0]["status"]), (200, "processed"))
        self.assertEqual(self.anonymized(), 0)
        self.assertEqual(self.record(), {"job_done": False, "event_done": True, "queue": []})

    def test_row_14_approved_deletion_plan_stays_the_jobs_plan(self) -> None:
        self.queue_the_delete_event()
        self.keycloak_answers("gone")
        preview = self.replay_preview()
        # Check at execution: 1 read. Every later read answers with a user.
        self.keycloak_answers("gone", "open")

        status, reply = self.replay(preview)

        self.assertEqual((status, reply["results"][0]["status"]), (200, "processed"))
        self.assertEqual(self.anonymized(), 2)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    def test_row_15_changed_answer_before_the_check_needs_a_new_preview(self) -> None:
        for first, then in (("closed", "gone"), ("gone", "closed")):
            with self.subTest(first=first, then=then):
                self.queue_the_delete_event()
                self.keycloak_answers(first)
                preview = self.replay_preview()
                self.keycloak_answers(then)

                status, reply = self.replay(preview, approval=f"onay-{first}")

                self.assertEqual((status, reply), (409, {"error": "preview_changed"}))
                self.assertEqual(self.writes(), 0)
                self.assertEqual(self.record(), {"job_done": False, "event_done": False, "queue": ["e-del"]})

    def test_row_16_event_after_a_finished_job_needs_no_keycloak_answer(self) -> None:
        # The job is finished and Keycloak cannot be read. The finished record alone decides:
        # the event is a duplicate. It is not queued, so nothing is left to replay.
        self.press_request()
        self.keycloak_answers("error")
        before = self.writes()

        reply = self.delete_event()

        self.assertEqual(reply["status"], "duplicate")
        self.assertEqual(self.writes(), before)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})
        self.assertEqual(self.replay_preview()["results"], [])

    # --- row 17: reconcile, when the delete event never arrived ---

    def test_row_17_reconcile_finishes_a_missed_delete(self) -> None:
        self.stack.keycloak.remove_user(SUBJECT)
        self.stack.keycloak.serve_directory()
        status, preview = self.post_json("/v1/reconcile", {"dry_run": True}, PREVIEW_TOKEN)
        self.assertEqual([p["operation"] for p in preview["previews"]], [*CLOSE, *ANONYMIZE])
        # The difference names the user by `sub`: the contract defines that field for this reader.
        self.assertEqual({d["kind"] for d in preview["differences"]}, {"deleted_in_keycloak"})
        self.seen((status, preview["previews"]))

        execute = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-m1"}
        status, done = self.post_json("/v1/reconcile", execute)

        self.seen((status, done["results"]))
        self.assertEqual(done["results"], [{"operation": "account_deletion", "target": self.job_id, "status": "done"}])
        self.assertEqual(self.anonymized(), 2)
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    # --- rows 18 and 19: nothing keeps the id once the job is done ---

    def leftovers(self) -> None:
        """Older records of the same user: a stopped invitation and a queued event."""
        from identity_sync.events import Event

        self.store.operation_begin("o-old", "invite_user", ORG_ID, ["s1"])
        self.store.operation_subject("o-old", SUBJECT)
        old = Event(id="e-old", kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=SUBJECT)
        self.store.add_dead_letter(old, "tenant.provision kiraci1: HTTP 503")

    def stored_text(self) -> str:
        return "\n".join(self.store._db.iterdump())

    def test_row_18_finished_job_leaves_the_id_in_no_record(self) -> None:
        self.leftovers()

        reply = self.press_request()

        self.assertEqual(reply["status"], "processed")
        self.assertNotIn(SUBJECT, self.stored_text())
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})
        self.seen(self.call("GET", "/v1/operations", None, self.bearer(PREVIEW_TOKEN)))

    def test_row_19_finished_record_and_cleanup_are_one_transaction(self) -> None:
        # The storage fails exactly when the id is cleaned up. Then the job must not count as
        # finished either, so the retry cleans up instead of answering "duplicate".
        self.leftovers()
        real = self.store._db

        class FailingOnCleanup:
            def __getattr__(self, name: str) -> object:
                return getattr(real, name)

            def execute(self, sql: str, *args: object) -> object:
                if "operations SET subject = ''" in sql:
                    raise sqlite3.OperationalError("disk I/O error")
                return real.execute(sql, *args)

        self.store._db = FailingOnCleanup()
        status, reply = self.post_json(
            "/v1/account-deletions",
            {"issuer": self.stack.issuer, "subject": SUBJECT, "reauthenticated_at": NOW - 10},
            PRESS_TOKEN,
        )
        self.store._db = real
        self.seen((status, reply))

        self.assertEqual((status, reply), (500, {"error": "storage_failed"}))
        self.assertFalse(self.store.is_processed(self.job_id))
        before = self.writes()

        retry = self.press_request()

        # Every step was finished before, so the retry writes to no target. It only records.
        self.assertEqual((retry["status"], retry["actions"]), ("processed", []))
        self.assertEqual(self.writes(), before)
        self.assertNotIn(SUBJECT, self.stored_text())
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})

    # --- rows 20 and 21: a finished deletion is never undone by an older or later event ---

    def test_row_20_event_queued_next_to_the_job_does_not_write_the_id_back(self) -> None:
        # The queue holds the deletion job and an older event of the same user. One approved
        # replay runs both. The job finishes first and cleans the records. The older event was
        # read into memory before that. It must not be recorded again, even if its target fails.
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        self.press_request()
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, fakes.DONE)
        self.leftovers()
        self.assertEqual(self.record()["queue"], [self.job_id, "e-old"])
        preview = self.replay_preview()
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (503, None))  # the older event's target fails
        before = self.writes()

        status, reply = self.replay(preview)

        self.assertEqual(status, 200)
        self.assertEqual([r["status"] for r in reply["results"]], ["processed", "duplicate"])
        # Only the job's two remaining steps were written. The older event wrote nothing.
        self.assertEqual(self.writes(), before + 2)
        self.assertNotIn(SUBJECT, self.stored_text())
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})
        self.queue_listing()

    def test_row_21_late_event_of_a_deleted_account_is_not_recorded(self) -> None:
        # The job is done. Later an event of the same account arrives and its target would fail.
        # The service knows the account only by the keyed digest of the finished job. It writes
        # nothing to a target and nothing to its own records.
        self.press_request()
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (503, None))
        before = self.writes()
        late = {"id": "e-late", "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 9, "user_id": SUBJECT}

        reply = self.seen(self.post_event(late))

        self.assertEqual(reply["status"], "duplicate")
        self.assertEqual(self.writes(), before)
        self.assertNotIn(SUBJECT, self.stored_text())
        self.assertFalse(self.store.is_processed("e-late"))
        self.assertEqual(self.record(), {"job_done": True, "event_done": False, "queue": []})
        self.queue_listing()
