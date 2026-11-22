"""H-5: an account deletion whose tenant step timed out settles by itself.

The final MVP test saw this: the tenant call of step 4 timed out after 10 seconds. The job stayed
`unknown`. The tenant finished the work 2 seconds later. The Keycloak user was never deleted.

Expected behaviour (docs/sozlesmeler.md, section 7, and contracts/identity_sync.openapi.yaml):

1. The service does not repeat the anonymize call blindly.
2. On the next request for the job, or while it handles the next event, the service asks the
   target for the state. The tenant's identity list no longer carries an anonymized identity.
3. When the target confirms the step, the job goes on from the next step and deletes the
   Keycloak user. When the target still lists the identity, the job stays `unknown`.

The fake tenant answers later than the timeout. The real case was 12 seconds against 10. The test
keeps the same order with shorter times, so the run stays short.
"""

from __future__ import annotations

import threading
import time

from . import fakes
from .fakes import ORG_ID, SUBJECT
from .test_server import NOW, PRESS_TOKEN, ServerCase

TIMEOUT = 0.3
LATE = 0.6
OTHER_EVENT = {"id": "e-other", "kind": "user", "type": "UPDATE_EMAIL", "realm": "platform", "time": 2,
               "user_id": "33333333-3333-4333-8333-333333333333"}


class UnknownDeletionTest(ServerCase):
    stack_settings = {"anonymize_timeout": TIMEOUT}

    def setUp(self) -> None:
        super().setUp()
        issuer = self.stack.issuer
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID, api_keys=1)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        self.job_id = self.stack.app.processor.account_job(SUBJECT, time=0).id
        self.finished = threading.Event()

    def tenant_answers_late(self, *, completes: bool = True) -> None:
        """The tenant answers after the timeout. With `completes` it has done the work by then."""
        tenant = self.stack.tenant
        work = tenant._defaults[("POST", fakes.TENANT_ANONYMIZE)]

        def late(req: fakes.Recorded) -> fakes.Reply:
            time.sleep(LATE)
            reply = work(req) if completes else fakes.frappe_error(500, "InternalError")
            self.finished.set()
            return reply

        tenant.on("POST", fakes.TENANT_ANONYMIZE, late)

    def press_request(self) -> dict:
        body = {"issuer": self.stack.issuer, "subject": SUBJECT, "reauthenticated_at": int(self.now) - 10}
        status, reply = self.post_json("/v1/account-deletions", body, PRESS_TOKEN)
        self.assertEqual(status, 200)
        return reply

    def first_request_times_out(self) -> None:
        reply = self.press_request()
        self.assertEqual(reply["status"], "unknown")
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertTrue(self.finished.wait(5))

    def tenant_anonymize_calls(self) -> int:
        return len(self.stack.tenant.calls("POST", fakes.TENANT_ANONYMIZE))

    def test_next_request_settles_a_timed_out_tenant_step(self) -> None:
        self.tenant_answers_late()
        self.first_request_times_out()

        reply = self.press_request()

        self.assertEqual(reply["status"], "processed")
        self.assertEqual(reply["actions"], ["keycloak.delete_user"])
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        # The state came from the identity list. The anonymize call was not repeated.
        self.assertEqual(self.tenant_anonymize_calls(), 1)
        self.assertTrue(self.stack.app.store.is_processed(self.job_id))

    def test_next_event_settles_a_timed_out_tenant_step(self) -> None:
        self.tenant_answers_late()
        self.first_request_times_out()

        status, _reply = self.post_event(OTHER_EVENT)

        self.assertEqual(status, 202)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.tenant_anonymize_calls(), 1)
        self.assertTrue(self.stack.app.store.is_processed(self.job_id))

    def test_step_stays_unknown_while_the_tenant_still_lists_the_identity(self) -> None:
        self.tenant_answers_late(completes=False)
        self.first_request_times_out()

        reply = self.press_request()
        self.post_event(OTHER_EVENT)

        self.assertEqual(reply["status"], "unknown")
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.tenant_anonymize_calls(), 1)
        self.assertEqual(self.stack.app.store.dead_letter_state(self.job_id), "unknown")

    def test_failed_state_read_keeps_the_step_unknown(self) -> None:
        self.tenant_answers_late()
        self.first_request_times_out()
        self.stack.tenant.on("GET", fakes.TENANT_LIST, (500, None))

        reply = self.press_request()

        self.assertEqual(reply["status"], "unknown")
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.tenant_anonymize_calls(), 1)

    def test_timed_out_press_step_settles_the_same_way(self) -> None:
        press = self.stack.press
        work = press._defaults[("POST", fakes.PRESS_ANONYMIZE)]

        def late(req: fakes.Recorded) -> fakes.Reply:
            time.sleep(LATE)
            reply = work(req)
            self.finished.set()
            return reply

        press.on("POST", fakes.PRESS_ANONYMIZE, late)
        self.first_request_times_out()

        reply = self.press_request()

        self.assertEqual(reply["status"], "processed")
        self.assertEqual(reply["actions"], ["tenant.anonymize_user", "keycloak.delete_user"])
        self.assertEqual(len(press.calls("POST", fakes.PRESS_ANONYMIZE)), 1)
        self.assertNotIn(SUBJECT, self.stack.keycloak.users)

    def test_other_calls_keep_the_general_timeout(self) -> None:
        # Only the anonymize calls wait longer. A slow tenant list read still uses the general timeout.
        self.assertEqual(self.stack.settings.http_timeout, 5.0)
        self.assertEqual(self.stack.settings.anonymize_timeout, TIMEOUT)
