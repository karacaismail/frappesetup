"""AtonotA Login verification inbox endpoint over the real HTTP path (G-164, AJA-231).

Expected behavior comes from the task AJA-231, the architecture note of AJA-213 and the contract
(`contracts/platform_core-identity.openapi.yaml`, tag `atonota-login`):
- the endpoint is open to guests; the provider carries no session,
- the signature is checked on the raw request body; a bad signature gets 401 and opens no record,
- the provider's event id is unique: the same notice twice gives one record,
- `process` does not run in the request; it is handed to `frappe.enqueue`,
- the endpoint has a rate limit like `keycloak_backchannel_logout`,
- document images and face data never reach a record or a log,
- no scheduled job is added; `replay_unknown` runs by hand only.
"""

import hashlib
import hmac
import json
import secrets
import time
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client

from platform_core.identity.atonota import verification_api
from platform_core.identity.tests import helpers as h

ENDPOINT = "/api/method/platform_core.api.atonota_login.verification_notice"
NOTICE = "PLT Verification Notice"
CASE = "PLT Verification Case"
SECRET = secrets.token_hex(32)
CASE_PREFIX = "aja231-"
# The fields a notice record may carry. Anything else could hold provider data.
NOTICE_FIELDS = {"event_id", "case_id", "attempt", "outcome", "state"}


def signature(body: bytes, secret: str = SECRET, stamp: int | None = None) -> str:
	stamp = int(time.time()) if stamp is None else stamp
	digest = hmac.new(secret.encode(), str(stamp).encode() + b"." + body, hashlib.sha256).hexdigest()
	return f"t={stamp},v1={digest}"


def notice_body(
	event: str, attempt: int = 1, outcome: str = "approved", case: str = "case-1", **extra
) -> bytes:
	return json.dumps(
		{"event_id": event, "case_id": CASE_PREFIX + case, "attempt": attempt, "outcome": outcome, **extra}
	).encode()


def clear_records() -> None:
	frappe.db.delete(NOTICE, {"case_id": ("like", f"{CASE_PREFIX}%")})
	frappe.db.delete(CASE, {"case_id": ("like", f"{CASE_PREFIX}%")})
	frappe.db.commit()  # nosemgrep: frappe-manual-commit


class TestAtonotaVerificationEndpoint(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		clear_records()
		h.reset_rate_limits()
		settings = h.SiteSettings({"atonota_verification_secret": SECRET})
		settings.__enter__()
		self.addCleanup(settings.__exit__, None, None, None)
		self.addCleanup(clear_records)

	# --- request helpers ---

	def post(self, body: bytes, header: str | None = None, content_type: str = "application/json"):
		headers = {"Accept": "application/json", "Content-Type": content_type}
		if header is not None:
			headers[verification_api.SIGNATURE_HEADER] = header
		kwargs = {"path": ENDPOINT, "method": "POST", "headers": headers, "data": body}
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		try:
			return make_request(get_test_client().open, args=(), kwargs=kwargs, site=frappe.local.site)
		finally:
			frappe.db.rollback()

	def send(self, body: bytes):
		return self.post(body, signature(body))

	def notices(self, **filters) -> list:
		return frappe.get_all(
			NOTICE,
			filters={"case_id": ("like", f"{CASE_PREFIX}%"), **filters},
			fields=["*"],
			order_by="creation asc",
		)

	# --- signature ---

	def test_bad_signature_is_refused_and_opens_no_record(self):
		body = notice_body("e-bad")
		tampered = body.replace(b"approved", b"rejected")
		cases = {
			"tampered body": (tampered, signature(body)),
			"no header": (body, None),
			"other secret": (body, signature(body, secrets.token_hex(32))),
			"old time": (body, signature(body, stamp=int(time.time()) - 3600)),
		}
		with mock.patch("frappe.enqueue") as enqueue:
			for name, (raw, header) in cases.items():
				with self.subTest(name):
					response = self.post(raw, header)
					self.assertEqual(response.status_code, 401, response.data[:300])
					self.assertEqual(response.json.get("exc_type"), "NoticeSignatureRejected")
		self.assertEqual(self.notices(), [])
		self.assertEqual(frappe.db.count(CASE, {"case_id": ("like", f"{CASE_PREFIX}%")}), 0)
		enqueue.assert_not_called()

	def test_signature_is_checked_on_the_raw_body(self):
		# Same JSON with other spacing: the parsed fields match, the raw bytes do not.
		body = notice_body("e-raw")
		respaced = json.dumps(json.loads(body), indent=1).encode()
		response = self.post(respaced, signature(body))
		self.assertEqual(response.status_code, 401, response.data[:300])
		self.assertEqual(self.notices(), [])

	def test_no_secret_means_configuration_required(self):
		body = notice_body("e-unset")
		with h.SiteSettings({"atonota_verification_secret": None}):
			response = self.send(body)
		self.assertEqual(response.status_code, 503, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "VerificationNotConfigured")
		self.assertEqual(self.notices(), [])

	def test_valid_notice_with_bad_fields_is_refused(self):
		body = notice_body("e-field", outcome="approve-everything")
		response = self.send(body)
		self.assertEqual(response.status_code, 400, response.data[:300])
		self.assertEqual(response.json.get("exc_type"), "InvalidInput")
		self.assertEqual(self.notices(), [])

	# --- one record per event ---

	def test_same_event_twice_gives_one_record(self):
		body = notice_body("e-twice")
		with mock.patch("frappe.enqueue") as enqueue:
			first = self.send(body)
			second = self.send(body)
		self.assertEqual(first.status_code, 200, first.data[:300])
		self.assertEqual(first.json["message"], {"status": "accepted"})
		self.assertEqual(second.status_code, 200, second.data[:300])
		self.assertEqual(second.json["message"], {"status": "duplicate"})
		self.assertEqual(len(self.notices(event_id="e-twice")), 1)
		# A duplicate gives the queue no new work.
		self.assertEqual(enqueue.call_count, 1)

	def test_event_id_is_unique_in_the_database(self):
		# Two inserts that pass the existence check at the same time still give one record.
		verification_api.FrappeNoticeStore().add_notice("e-race", CASE_PREFIX + "case-1", 1, "approved")
		with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
			frappe.get_doc(
				{
					"doctype": NOTICE,
					"event_id": "e-race",
					"case_id": CASE_PREFIX + "case-1",
					"attempt": 1,
					"outcome": "approved",
					"state": "pending",
				}
			).db_insert()
		frappe.db.rollback()

	# --- queue ---

	def test_process_is_queued_not_run_in_the_request(self):
		verification_api.open_attempt(CASE_PREFIX + "case-1")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		with mock.patch("frappe.enqueue") as enqueue:
			response = self.send(notice_body("e-queue"))
		self.assertEqual(response.status_code, 200, response.data[:300])
		enqueue.assert_called_once()
		args, kwargs = enqueue.call_args
		self.assertEqual(args[0], verification_api.PROCESS_JOB)
		self.assertTrue(kwargs.get("enqueue_after_commit"))
		self.assertFalse(kwargs.get("now"))
		# The request stored the notice and stopped. Nothing is applied yet.
		self.assertEqual([row.state for row in self.notices()], ["pending"])
		self.assertEqual(verification_api.decision(CASE_PREFIX + "case-1"), "pending")
		# The queue worker runs the job later.
		self.assertEqual(frappe.get_attr(verification_api.PROCESS_JOB)(), [("e-queue", "applied")])
		self.assertEqual(verification_api.decision(CASE_PREFIX + "case-1"), "approved")

	def test_doctype_store_keeps_the_inbox_rules(self):
		case = CASE_PREFIX + "case-1"
		verification_api.open_attempt(case)
		verification_api.open_attempt(case)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		with mock.patch("frappe.enqueue"):
			for event, attempt, outcome in (
				("e-new", 2, "rejected"),
				("e-old", 1, "approved"),
				("e-unk", 9, "approved"),
			):
				self.assertEqual(self.send(notice_body(event, attempt, outcome)).status_code, 200)
		self.assertEqual(
			verification_api.process_notices(),
			[("e-new", "applied"), ("e-old", "stale"), ("e-unk", "unknown-attempt")],
		)
		self.assertEqual(verification_api.decision(case), "rejected")
		# A new attempt makes the case pending again.
		verification_api.open_attempt(case)
		self.assertEqual(verification_api.decision(case), "pending")

	def test_replay_unknown_runs_by_hand_for_the_system_manager_only(self):
		with mock.patch("frappe.enqueue"):
			self.send(notice_body("e-later", 1, "approved"))
		self.assertEqual(verification_api.process_notices(), [("e-later", "unknown-attempt")])
		verification_api.open_attempt(CASE_PREFIX + "case-1")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			verification_api.replay_unknown()
		frappe.set_user("Administrator")
		with mock.patch("frappe.enqueue") as enqueue:
			self.assertEqual(verification_api.replay_unknown(), 1)
		self.assertEqual(enqueue.call_args.args[0], verification_api.PROCESS_JOB)
		self.assertEqual(verification_api.process_notices(), [("e-later", "applied")])

	def test_no_scheduled_job_is_added(self):
		from platform_core import hooks

		scheduled = json.dumps(getattr(hooks, "scheduler_events", {}))
		self.assertNotIn("atonota", scheduled)
		self.assertNotIn("verification", scheduled)
		for jobs in frappe.get_hooks("scheduler_events").values():
			flat = json.dumps(jobs)
			self.assertNotIn("verification_api", flat)

	# --- rate limit ---

	def test_rate_limit_refuses_extra_requests(self):
		statuses = []
		for _number in range(verification_api.RATE_LIMIT + 1):
			response = self.post(b"{}", "t=0,v1=00")
			statuses.append(response.status_code)
			if response.status_code == 429:
				break
		self.assertEqual(statuses[-1], 429, statuses[-3:])
		self.assertEqual(len(statuses), verification_api.RATE_LIMIT + 1)
		self.assertEqual(set(statuses[:-1]), {401})

	# --- no raw document or face data ---

	def test_raw_document_and_face_data_are_not_stored(self):
		marker = secrets.token_hex(12)
		verification_api.open_attempt(CASE_PREFIX + "case-1")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		body = notice_body("e-raw-data", document_image=marker, face_scan=marker, selfie=marker)
		with mock.patch("frappe.enqueue"):
			self.assertEqual(self.send(body).status_code, 200)
		verification_api.process_notices()
		rows = self.notices()
		self.assertEqual(len(rows), 1)
		self.assertNotIn(marker, json.dumps(rows, default=str))
		cases = frappe.get_all(CASE, filters={"case_id": ("like", f"{CASE_PREFIX}%")}, fields=["*"])
		self.assertNotIn(marker, json.dumps(cases, default=str))
		meta_fields = {df.fieldname for df in frappe.get_meta(NOTICE).fields}
		self.assertEqual(meta_fields, NOTICE_FIELDS)
		self.assertFalse(frappe.get_meta(NOTICE).track_changes)

	def test_server_error_keeps_raw_data_out_of_the_error_log(self):
		# Frappe copies JSON body fields into form_dict and logs form_dict on a 5xx error.
		marker = secrets.token_hex(12)
		body = notice_body("e-crash", document_image=marker, face_scan=marker)
		before = set(frappe.get_all("Error Log", pluck="name"))
		with mock.patch.object(
			verification_api.FrappeNoticeStore, "add_notice", side_effect=RuntimeError("boom")
		):
			response = self.send(body)
		self.assertEqual(response.status_code, 500, response.data[:300])
		self.assertNotIn(marker.encode(), response.data)
		logs = [row for row in frappe.get_all("Error Log", fields=["*"]) if row.name not in before]
		self.assertTrue(logs, "the safe error wrapper writes one entry")
		self.assertNotIn(marker, json.dumps(logs, default=str))
		self.assertEqual(self.notices(), [])

	def test_endpoint_is_open_to_guests_and_post_only(self):
		from platform_core.api import atonota_login

		function = atonota_login.verification_notice
		self.assertIn(function, frappe.guest_methods)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(function), ["POST"])
		self.assertNotIn(
			"platform_core.api.atonota_login.verification_notice",
			frappe.get_hooks("website_user_allowed_methods"),
		)
