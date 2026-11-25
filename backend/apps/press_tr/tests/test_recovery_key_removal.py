"""AJA-420: after an approved recovery, Press asks identity-sync to remove the old keys.

The design is in AJA-426:
- the record goes from Approved to Completed, or to Removal Failed when the service fails;
- only the removal step writes these states; a desk form or API write cannot set them;
- a person with write permission who is not the account owner starts the removal;
- a Completed record does not call the service again;
- the error field holds a short code, never personal data.
"""

import ast
import json
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1] / "press_tr"
DOCTYPE_DIR = APP / "press_identity/doctype/ptr_recovery_review"
REVIEW_FIELDS = {
	"identity_link": "link-1",
	"requested_at": "2026-11-20 10:00:00",
	"review_note": "Identity confirmed by phone call.",
	"reviewed_by": "reviewer@example.test",
	"reviewed_at": "2026-11-21 09:00:00",
}
EMPTY_REMOVAL = {"removal_attempted_at": None, "removal_error": None, "completed_at": None}


def _framework(session_user="reviewer@example.test"):
	framework = Mock()
	framework.session = SimpleNamespace(user=session_user)
	framework.throw.side_effect = PermissionError
	framework.PermissionError = PermissionError
	framework.db.get_value.side_effect = lambda doctype, name, column, **kwargs: "customer@example.test"
	framework.utils.get_datetime.side_effect = lambda value: (
		value if isinstance(value, datetime) else datetime.fromisoformat(value)
	)
	return framework


class KeyRemovalStateTest(unittest.TestCase):
	"""The removal states in `check_decision`. Every write goes through this check."""

	def setUp(self):
		from press_tr.press_identity import recovery

		self.recovery = recovery

	def _save(self, before, after, *, flag=False, changes=None, removal_before=None):
		stored = {**REVIEW_FIELDS, **EMPTY_REMOVAL, **(removal_before or {}), "status": before}
		previous = SimpleNamespace(**stored)
		doc = SimpleNamespace(**stored, get_doc_before_save=lambda: previous)
		doc.flags = SimpleNamespace(key_removal=True) if flag else SimpleNamespace()
		doc.status = after
		for field, value in (changes or {}).items():
			setattr(doc, field, value)
		with (
			patch.object(self.recovery, "frappe", _framework()),
			patch.object(self.recovery, "_", lambda text, context=None: text),
		):
			self.recovery.check_decision(doc)
		return doc

	def test_removal_step_moves_an_approved_record_on(self):
		attempt = {"removal_attempted_at": "2026-11-22 08:00:00"}
		self._save("Approved", "Completed", flag=True, changes={**attempt, "completed_at": "2026-11-22 08:00:00"})
		self._save("Approved", "Removal Failed", flag=True, changes={**attempt, "removal_error": "upstream_failed"})
		failed = {**attempt, "removal_error": "upstream_failed"}
		self._save("Removal Failed", "Removal Failed", flag=True, removal_before=failed, changes={"removal_error": "unknown"})
		self._save(
			"Removal Failed",
			"Completed",
			flag=True,
			removal_before=failed,
			changes={"removal_error": None, "completed_at": "2026-11-22 08:05:00"},
		)

	def test_desk_or_api_write_cannot_set_the_new_states(self):
		for before, after in (
			("Approved", "Completed"),
			("Approved", "Removal Failed"),
			("Removal Failed", "Completed"),
			("Open", "Completed"),
			("Open", "Removal Failed"),
		):
			with self.subTest(before=before, after=after), self.assertRaises(PermissionError):
				self._save(before, after)

	def test_desk_or_api_write_cannot_change_the_removal_fields(self):
		for field, value in (
			("removal_attempted_at", "2026-11-22 08:00:00"),
			("removal_error", "upstream_failed"),
			("completed_at", "2026-11-22 08:00:00"),
		):
			for status in ("Approved", "Removal Failed", "Open"):
				with self.subTest(field=field, status=status), self.assertRaises(PermissionError):
					self._save(status, status, changes={field: value})

	def test_removal_step_cannot_change_the_review_fields(self):
		changes = {
			"identity_link": "link-own",
			"review_note": "Changed later.",
			"reviewed_by": "someone-else@example.test",
			"reviewed_at": "2026-11-22 08:00:00",
			"requested_at": "2026-11-22 08:00:00",
		}
		for field, value in changes.items():
			with self.subTest(field=field), self.assertRaises(PermissionError):
				self._save("Approved", "Completed", flag=True, changes={field: value})

	def test_completed_and_rejected_are_final_even_for_the_removal_step(self):
		for before, after in (
			("Completed", "Removal Failed"),
			("Completed", "Approved"),
			("Rejected", "Completed"),
			("Rejected", "Removal Failed"),
		):
			with self.subTest(before=before, after=after), self.assertRaises(PermissionError):
				self._save(before, after, flag=True)
		with self.assertRaises(PermissionError):
			self._save("Completed", "Completed", flag=True, changes={"removal_error": "unknown"})

	def test_removal_step_cannot_skip_the_decision(self):
		for before, after in (("Open", "Completed"), ("Open", "Removal Failed"), ("Approved", "Rejected"), ("Approved", "Open")):
			with self.subTest(before=before, after=after), self.assertRaises(PermissionError):
				self._save(before, after, flag=True)

	def test_new_record_cannot_arrive_with_removal_fields(self):
		for field in EMPTY_REMOVAL:
			doc = SimpleNamespace(
				**REVIEW_FIELDS,
				**EMPTY_REMOVAL,
				status="Open",
				get_doc_before_save=lambda: None,
			)
			doc.reviewed_by = doc.reviewed_at = None
			setattr(doc, field, "2026-11-22 08:00:00")
			with (
				self.subTest(field=field),
				patch.object(self.recovery, "frappe", _framework()),
				patch.object(self.recovery, "_", lambda text, context=None: text),
				self.assertRaises(PermissionError),
			):
				self.recovery.check_decision(doc)

	def test_decision_still_needs_a_note_and_a_non_owner(self):
		# The Open to Approved rule of AJA-354 stays as it was.
		stored = {**REVIEW_FIELDS, **EMPTY_REMOVAL, "status": "Open", "reviewed_by": None, "reviewed_at": None}
		previous = SimpleNamespace(**stored)
		doc = SimpleNamespace(**stored, get_doc_before_save=lambda: previous)
		doc.status = "Approved"
		framework = _framework()
		with (
			patch.object(self.recovery, "frappe", framework),
			patch.object(self.recovery, "_", lambda text, context=None: text),
		):
			self.recovery.check_decision(doc)
		self.assertEqual(doc.reviewed_by, "reviewer@example.test")


class RemoveRecoveredKeysTest(unittest.TestCase):
	"""`remove_recovered_keys` with a fake identity-sync service."""

	def setUp(self):
		from press_tr.press_identity import recovery_keys

		self.module = recovery_keys
		self.framework = _framework()
		self.framework.has_permission.return_value = True
		self.framework.utils.now_datetime.return_value = datetime(2026, 11, 22, 8, 0, 0)
		self.framework.utils.get_system_timezone.return_value = "UTC"
		self.link = SimpleNamespace(issuer="https://login.example.test/realms/platform", subject="sub-1")

		def get_value(doctype, name, column, **kwargs):
			if column == "user":
				return "customer@example.test"
			return self.link

		self.framework.db.get_value.side_effect = get_value
		self.service = Mock(return_value=2)
		self.session = Mock()

	def _doc(self, status, **removal):
		doc = SimpleNamespace(
			name="a1b2c3d4e5",
			status=status,
			**{**REVIEW_FIELDS, "reviewed_at": datetime(2026, 11, 21, 9, 0, 0)},
			**{**EMPTY_REMOVAL, **removal},
			flags=SimpleNamespace(),
		)
		doc.save = Mock()
		return doc

	def _call(self, doc, review="a1b2c3d4e5"):
		self.framework.get_doc.return_value = doc
		with (
			patch.object(self.module, "frappe", self.framework),
			patch.object(self.module, "_", lambda text, context=None: text),
			patch.object(self.module, "browser_session", self.session),
			patch.object(self.module, "send_key_removal_request", self.service),
		):
			return self.module.remove_recovered_keys(review)

	def test_approved_record_removes_the_keys_and_completes(self):
		doc = self._doc("Approved")

		result = self._call(doc)

		self.assertEqual(result, {"status": "Completed"})
		approved_at = int(datetime(2026, 11, 21, 9, 0, 0).timestamp() - datetime(1970, 1, 1).timestamp())
		self.service.assert_called_once_with(self.link, "a1b2c3d4e5", approved_at)
		self.framework.get_doc.assert_called_once_with("PTR Recovery Review", "a1b2c3d4e5", for_update=True)
		self.assertEqual(doc.status, "Completed")
		self.assertTrue(doc.flags.key_removal)
		self.assertEqual(doc.removal_attempted_at, datetime(2026, 11, 22, 8, 0, 0))
		self.assertEqual(doc.completed_at, datetime(2026, 11, 22, 8, 0, 0))
		self.assertIsNone(doc.removal_error)
		doc.save.assert_called_once_with()

	def test_approval_time_is_read_in_the_system_time_zone(self):
		# Frappe stores 09:00 Istanbul time without the zone. In UTC that is 06:00.
		self.framework.utils.get_system_timezone.return_value = "Europe/Istanbul"
		with patch.object(self.module, "frappe", self.framework):
			seconds = self.module.approved_at_seconds(datetime(2026, 11, 21, 9, 0, 0))
		self.assertEqual(seconds, int((datetime(2026, 11, 21, 6, 0, 0) - datetime(1970, 1, 1)).total_seconds()))

	def test_failed_removal_keeps_the_record_open_with_the_error(self):
		from press_tr.press_identity.deletion import KeyRemovalFailed

		for code in ("not_configured", "upstream_failed", "unknown"):
			with self.subTest(code=code):
				self.service = Mock(side_effect=KeyRemovalFailed(code))
				doc = self._doc("Approved")

				result = self._call(doc)

				self.assertEqual(result, {"status": "Removal Failed", "error": code})
				self.assertEqual((doc.status, doc.removal_error), ("Removal Failed", code))
				self.assertIsNone(doc.completed_at)
				self.assertEqual(doc.removal_attempted_at, datetime(2026, 11, 22, 8, 0, 0))
				doc.save.assert_called_once_with()

	def test_failed_record_can_be_tried_again(self):
		doc = self._doc("Removal Failed", removal_error="upstream_failed", removal_attempted_at=datetime(2026, 11, 21, 10, 0))

		self.assertEqual(self._call(doc), {"status": "Completed"})
		self.assertIsNone(doc.removal_error)
		self.service.assert_called_once()

	def test_completed_record_does_not_call_the_service_again(self):
		doc = self._doc("Completed", completed_at=datetime(2026, 11, 21, 10, 0))

		self.assertEqual(self._call(doc), {"status": "Completed"})
		self.service.assert_not_called()
		doc.save.assert_not_called()

	def test_open_or_rejected_record_removes_no_key(self):
		for status in ("Open", "Rejected"):
			with self.subTest(status=status), self.assertRaises(PermissionError):
				self._call(self._doc(status))
		self.service.assert_not_called()

	def test_account_owner_and_guest_cannot_call(self):
		for user in ("customer@example.test", "Guest"):
			self.framework.session = SimpleNamespace(user=user)
			doc = self._doc("Approved")
			with self.subTest(user=user), self.assertRaises(PermissionError):
				self._call(doc)
			doc.save.assert_not_called()
		self.service.assert_not_called()

	def test_caller_without_write_permission_is_refused_before_the_record_is_locked(self):
		self.framework.has_permission.return_value = False

		with self.assertRaises(PermissionError):
			self._call(self._doc("Approved"))
		self.framework.has_permission.assert_called_once_with("PTR Recovery Review", "write")
		self.framework.has_permission.reset_mock()
		self.framework.has_permission.side_effect = [True, False]
		with self.assertRaises(PermissionError):
			self._call(self._doc("Approved"))
		self.assertEqual(self.framework.has_permission.call_args.args, ("PTR Recovery Review", "write", "a1b2c3d4e5"))
		self.framework.get_doc.assert_not_called()
		self.service.assert_not_called()

	def test_token_or_impersonated_request_is_refused_first(self):
		self.session.side_effect = PermissionError

		with self.assertRaises(PermissionError):
			self._call(self._doc("Approved"))
		self.framework.has_permission.assert_not_called()
		self.service.assert_not_called()

	def test_review_name_must_be_text(self):
		for review in ("", None, 5, ["a1b2c3d4e5"]):
			with self.subTest(review=review), self.assertRaises(PermissionError):
				self._call(self._doc("Approved"), review=review)
		self.service.assert_not_called()


class KeyRemovalRequestTest(unittest.TestCase):
	"""`send_key_removal_request` talks to identity-sync and maps every failure to a short code."""

	def setUp(self):
		from press_tr.press_identity import deletion

		self.deletion = deletion
		self.framework = Mock()
		self.framework.conf = SimpleNamespace(
			identity_sync_url="http://identity-sync.example.test:3205/",
			press_service_client_secret="test-only",
		)
		self.requests = Mock()
		self.requests.RequestException = deletion.requests.RequestException
		self.requests.ReadTimeout = deletion.requests.ReadTimeout
		self.token = Mock(status_code=200)
		self.token.json.return_value = {"access_token": "service-token"}
		self.reply = Mock(status_code=200)
		self.reply.raw.read.return_value = json.dumps({"status": "done", "removed": 2}).encode()
		self.requests.post.side_effect = [self.token, self.reply]
		self.link = SimpleNamespace(issuer="https://login.example.test/realms/platform", subject="sub-1")
		self.verify = Mock()
		self.framework.PermissionError = PermissionError

	def _send(self):
		with (
			patch.object(self.deletion, "frappe", self.framework),
			patch.object(self.deletion, "requests", self.requests),
			patch.object(self.deletion, "server_endpoint", lambda name: f"https://login.example.test/{name}"),
			patch.object(self.deletion, "verify", self.verify),
			patch.dict("sys.modules", {"oidc_verify": Mock()}),
		):
			return self.deletion.send_key_removal_request(self.link, "a1b2c3d4e5", 1_795_000_000)

	def _code(self):
		with self.assertRaises(self.deletion.KeyRemovalFailed) as caught:
			self._send()
		return caught.exception.code

	def test_service_removes_the_keys(self):
		self.assertEqual(self._send(), 2)
		token_call, call = self.requests.post.call_args_list
		self.assertEqual(token_call.kwargs["data"]["scope"], "aud-identity-sync")
		self.assertEqual(call.args[0], "http://identity-sync.example.test:3205/v1/recovery-key-removals")
		self.assertEqual(call.kwargs["headers"], {"Authorization": "Bearer service-token"})
		self.assertEqual(
			call.kwargs["json"],
			{
				"issuer": self.link.issuer,
				"subject": "sub-1",
				"review_id": "a1b2c3d4e5",
				"approved_at": 1_795_000_000,
			},
		)
		self.assertFalse(call.kwargs["allow_redirects"])

	def test_missing_settings_are_not_configured(self):
		self.framework.conf.identity_sync_url = None
		self.assertEqual(self._code(), "not_configured")
		self.requests.post.assert_not_called()

	def test_refused_token_is_an_upstream_failure(self):
		self.token.status_code = 401
		self.assertEqual(self._code(), "upstream_failed")

	def test_service_error_is_an_upstream_failure(self):
		for status in (400, 403, 502):
			with self.subTest(status=status):
				self.setUp()
				self.reply.status_code = status
				self.assertEqual(self._code(), "upstream_failed")

	def test_unclear_reply_is_an_upstream_failure(self):
		for body in (b"not json", b"[]", b'{"status": "done"}', b'{"status": "x", "removed": 1}', b'{"status": "done", "removed": true}'):
			with self.subTest(body=body):
				self.setUp()
				self.reply.raw.read.return_value = body
				self.assertEqual(self._code(), "upstream_failed")

	def test_rejected_service_token_is_an_upstream_failure(self):
		# The real check throws PermissionError for a bad token. The record must still get a code.
		self.verify = Mock(side_effect=PermissionError)
		self.assertEqual(self._code(), "upstream_failed")

	def test_unavailable_keycloak_keys_are_an_upstream_failure(self):
		self.verify = Mock(side_effect=self.deletion.ServiceUnavailable())
		self.assertEqual(self._code(), "upstream_failed")

	def test_late_reply_is_unknown(self):
		self.requests.post.side_effect = [self.token, self.deletion.requests.ReadTimeout()]
		self.assertEqual(self._code(), "unknown")

	def test_connection_error_is_an_upstream_failure(self):
		self.requests.post.side_effect = [self.token, self.deletion.requests.ConnectionError()]
		self.assertEqual(self._code(), "upstream_failed")

	def test_error_code_carries_no_personal_data(self):
		self.assertEqual(self.deletion.KEY_REMOVAL_ERRORS, ("not_configured", "upstream_failed", "unknown"))
		with self.assertRaises(ValueError):
			self.deletion.KeyRemovalFailed("customer@example.test")


class KeyRemovalRouteTest(unittest.TestCase):
	def _route(self):
		tree = ast.parse((APP / "api/account.py").read_text(encoding="utf-8"))
		return next(
			node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "remove_recovered_keys"
		)

	def test_route_is_a_post_for_signed_in_people_only(self):
		route = self._route()
		decorators = [ast.unparse(item) for item in route.decorator_list]
		self.assertEqual(decorators, ["frappe.whitelist(methods=['POST'])"])
		calls = {ast.unparse(node.func) for node in ast.walk(route) if isinstance(node, ast.Call)}
		self.assertIn("remove_recovered_keys_for_review", calls)
		self.assertIn("secrets.compare_digest", calls)

	def test_route_accepts_only_the_review_name(self):
		from press_tr.api import account

		framework = Mock()
		framework.get_request_header.return_value = "csrf-1"
		framework.session = SimpleNamespace(data={"csrf_token": "csrf-1"})
		removal = Mock(return_value={"status": "Completed"})
		with (
			patch.object(account, "frappe", framework),
			patch.object(account, "remove_recovered_keys_for_review", removal),
			patch.object(account, "reject", Mock(side_effect=PermissionError)),
		):
			framework.form_dict = {"cmd": "x", "review": "a1b2c3d4e5"}
			self.assertEqual(account.remove_recovered_keys("a1b2c3d4e5"), {"status": "Completed"})
			removal.assert_called_once_with("a1b2c3d4e5")
			framework.form_dict = {"cmd": "x", "review": "a1b2c3d4e5", "subject": "other"}
			with self.assertRaises(PermissionError):
				account.remove_recovered_keys("a1b2c3d4e5")
			framework.form_dict = {"cmd": "x", "review": "a1b2c3d4e5"}
			framework.get_request_header.return_value = "wrong"
			with self.assertRaises(PermissionError):
				account.remove_recovered_keys("a1b2c3d4e5")
		self.assertEqual(removal.call_count, 1)

	def test_review_doctype_lists_the_removal_states_and_fields(self):
		doc = json.loads((DOCTYPE_DIR / "ptr_recovery_review.json").read_text(encoding="utf-8"))
		fields = {field["fieldname"]: field for field in doc["fields"]}
		self.assertEqual(
			fields["status"]["options"].split("\n"), ["Open", "Approved", "Rejected", "Removal Failed", "Completed"]
		)
		for name in ("removal_attempted_at", "removal_error", "completed_at"):
			with self.subTest(field=name):
				self.assertIn(name, doc["field_order"])
				self.assertTrue(fields[name].get("read_only"))
				self.assertTrue(fields[name].get("description"))
		self.assertEqual(fields["removal_error"]["fieldtype"], "Data")
		self.assertTrue(doc["track_changes"])

	def test_desk_button_shows_only_while_removal_is_due(self):
		script = (DOCTYPE_DIR / "ptr_recovery_review.js").read_text(encoding="utf-8")
		self.assertIn("press_tr.api.account.remove_recovered_keys", script)
		self.assertIn('["Approved", "Removal Failed"].includes(frm.doc.status)', script)
		self.assertIn("frm.add_custom_button", script)
		self.assertIn("frm.reload_doc()", script)


if __name__ == "__main__":
	unittest.main()
