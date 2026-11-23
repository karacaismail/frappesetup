"""External verification result tests (G-164).

Expected rules, from G-164: with no provider chosen a required check does not start and the
result is "configuration required". A notice is checked against its signature first, over the
raw request body. A valid notice goes to a durable inbox. The same notice is not processed
twice. An old attempt cannot change a newer decision. Raw document and face data are not copied.
"""

import hashlib
import hmac
import json
import secrets
import tempfile
import time
import unittest
from pathlib import Path

from atonota_login import verification_inbox as inbox_module
from atonota_login.verification_inbox import ConfigurationRequired, HmacSignature, SignatureRejected, VerificationInbox


def signed(secret: bytes, body: bytes, stamp: int) -> dict:
    digest = hmac.new(secret, str(stamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return {inbox_module.SIGNATURE_HEADER: f"t={stamp},v1={digest}"}


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "inbox.sqlite3"
        self.secret = secrets.token_bytes(32)
        self.now = int(time.time())
        self.inbox = VerificationInbox(self.path, HmacSignature(self.secret))

    def notice(self, event, attempt, outcome, case="case-1", **extra):
        body = json.dumps({"event_id": event, "case_id": case, "attempt": attempt, "outcome": outcome, **extra}).encode()
        return body, signed(self.secret, body, self.now)

    def test_no_provider_means_configuration_required(self):
        empty = VerificationInbox(self.path, None)
        with self.assertRaises(ConfigurationRequired):
            empty.open_attempt("case-1")
        with self.assertRaises(ConfigurationRequired):
            empty.receive(b"{}", {}, self.now)

    def test_invalid_signature_is_refused(self):
        body, headers = self.notice("e1", 1, "approved")
        tampered = body.replace(b"approved", b"rejected")
        for raw, sent in ((tampered, headers), (body, {}), (body, signed(secrets.token_bytes(32), body, self.now))):
            with self.subTest(sent=sorted(sent)), self.assertRaises(SignatureRejected):
                self.inbox.receive(raw, sent, self.now)
        self.assertEqual(self.inbox.decision("case-1"), "pending")

    def test_signature_is_checked_on_the_raw_body(self):
        # Same JSON, other spacing: the signature no longer matches.
        body, headers = self.notice("e1", 1, "approved")
        respaced = json.dumps(json.loads(body), indent=1).encode()
        with self.assertRaises(SignatureRejected):
            self.inbox.receive(respaced, headers, self.now)

    def test_old_signature_time_is_refused(self):
        body, _ = self.notice("e1", 1, "approved")
        old = signed(self.secret, body, self.now - inbox_module.DEFAULT_TOLERANCE_SECONDS - 1)
        with self.assertRaises(SignatureRejected):
            self.inbox.receive(body, old, self.now)

    def test_same_notice_twice_changes_nothing(self):
        self.inbox.open_attempt("case-1")
        body, headers = self.notice("e1", 1, "approved")
        self.assertEqual(self.inbox.receive(body, headers, self.now), "accepted")
        self.assertEqual(self.inbox.process(), [("e1", "applied")])
        self.assertEqual(self.inbox.receive(body, headers, self.now), "duplicate")
        self.assertEqual(self.inbox.process(), [])
        self.assertEqual(self.inbox.decision("case-1"), "approved")

    def test_inbox_survives_a_restart(self):
        self.inbox.open_attempt("case-1")
        body, headers = self.notice("e1", 1, "approved")
        self.inbox.receive(body, headers, self.now)
        reopened = VerificationInbox(self.path, HmacSignature(self.secret))
        self.assertEqual(reopened.process(), [("e1", "applied")])
        self.assertEqual(reopened.decision("case-1"), "approved")

    def test_old_attempt_cannot_change_a_newer_decision(self):
        self.inbox.open_attempt("case-1")
        self.inbox.open_attempt("case-1")
        for event, attempt, outcome in (("new", 2, "rejected"), ("old", 1, "approved")):
            body, headers = self.notice(event, attempt, outcome)
            self.inbox.receive(body, headers, self.now)
        self.assertEqual(self.inbox.process(), [("new", "applied"), ("old", "stale")])
        self.assertEqual(self.inbox.decision("case-1"), "rejected")

    def test_unknown_attempt_is_not_applied(self):
        self.inbox.open_attempt("case-1")
        body, headers = self.notice("e9", 7, "approved")
        self.inbox.receive(body, headers, self.now)
        self.assertEqual(self.inbox.process(), [("e9", "unknown-attempt")])
        self.assertEqual(self.inbox.decision("case-1"), "pending")

    def test_browser_cannot_mark_a_case_complete(self):
        self.inbox.open_attempt("case-1")
        self.assertFalse(hasattr(self.inbox, "mark_complete"))
        self.assertEqual(self.inbox.decision("case-1"), "pending")

    def test_raw_document_and_face_data_are_not_stored(self):
        self.inbox.open_attempt("case-1")
        marker = secrets.token_hex(8)
        body, headers = self.notice("e1", 1, "approved", document_image=marker, face_scan=marker)
        self.inbox.receive(body, headers, self.now)
        self.inbox.process()
        self.inbox.close()
        self.assertNotIn(marker.encode(), self.path.read_bytes())

    def test_final_outcome_of_an_attempt_is_not_overwritten(self):
        # Review finding 2: a late notice for the same attempt must not reverse a final decision.
        for first, late in (("approved", "review"), ("rejected", "approved"), ("approved", "rejected")):
            with self.subTest(first=first, late=late):
                case = f"case-{first}-{late}"
                self.inbox.open_attempt(case)
                for event, outcome in ((f"{case}-a", first), (f"{case}-b", late)):
                    body, headers = self.notice(event, 1, outcome, case=case)
                    self.inbox.receive(body, headers, self.now)
                self.assertEqual(self.inbox.process(), [(f"{case}-a", "applied"), (f"{case}-b", "final-kept")])
                self.assertEqual(self.inbox.decision(case), first)

    def test_review_can_become_final(self):
        self.inbox.open_attempt("case-1")
        for event, outcome in (("e1", "review"), ("e2", "approved")):
            body, headers = self.notice(event, 1, outcome)
            self.inbox.receive(body, headers, self.now)
        self.assertEqual(self.inbox.process(), [("e1", "applied"), ("e2", "applied")])
        self.assertEqual(self.inbox.decision("case-1"), "approved")

    def test_new_attempt_makes_the_case_pending(self):
        # Review finding 3: a new check replaces the old result until the new result arrives.
        self.inbox.open_attempt("case-1")
        body, headers = self.notice("e1", 1, "approved")
        self.inbox.receive(body, headers, self.now)
        self.inbox.process()
        self.inbox.open_attempt("case-1")
        self.assertEqual(self.inbox.decision("case-1"), "pending")

    def test_unknown_attempt_can_be_replayed(self):
        # Review finding 7: the notice is kept and an operator can replay it.
        body, headers = self.notice("e1", 1, "approved")
        self.inbox.receive(body, headers, self.now)
        self.assertEqual(self.inbox.process(), [("e1", "unknown-attempt")])
        self.inbox.open_attempt("case-1")
        self.assertEqual(self.inbox.replay_unknown(), 1)
        self.assertEqual(self.inbox.process(), [("e1", "applied")])

    def test_malformed_signature_and_body_are_refused_cleanly(self):
        # Review finding 6: bad input gives the module's own errors, not a crash.
        body, _ = self.notice("e1", 1, "approved")
        with self.assertRaises(SignatureRejected):
            self.inbox.receive(body, {inbox_module.SIGNATURE_HEADER: f"t={self.now},v1=\u00e7ok"}, self.now)
        for raw in (b"[1, 2]", b"\xff\xfe"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.inbox.receive(raw, signed(self.secret, raw, self.now), self.now)

    def test_bad_outcome_is_refused(self):
        body, headers = self.notice("e1", 1, "approve-everything")
        with self.assertRaises(ValueError):
            self.inbox.receive(body, headers, self.now)


if __name__ == "__main__":
    unittest.main()
