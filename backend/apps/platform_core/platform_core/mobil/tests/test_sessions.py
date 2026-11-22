"""Regressions for Keycloak session binding and revocation."""

import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase


class MobileSessionTest(IntegrationTestCase):
	def setUp(self):
		self.account = (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": f"mobile-sid-{uuid4().hex}@example.test",
					"first_name": "Mobile Session Test",
					"send_welcome_email": 0,
				}
			)
			.insert()
			.name
		)
		self.sid = str(uuid4())
		self.identity = SimpleNamespace(
			account=self.account,
			site=frappe.local.site,
			scope="mobile",
			principal="fixture",
			issued_at=int(time.time()),
			sid=self.sid,
		)
		self.body = {"installation_id": str(uuid4())}

	def test_registration_persists_sid_and_does_not_replace_it(self):
		from platform_core.api.mobile import _register
		from platform_core.mobil.protocol import MobileError

		_register(self.identity, self.body)
		self.assertEqual(
			frappe.db.get_value("Mobile Installation", self.body["installation_id"], "session_id"), self.sid
		)
		with self.assertRaises(MobileError):
			_register(SimpleNamespace(**{**vars(self.identity), "sid": str(uuid4())}), self.body)

	def test_local_revocation_schedules_remote_close_only_after_commit(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobil.protocol import MobileError

		_register(self.identity, self.body)
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch("platform_core.mobil.sessions.send_session_revocations", return_value=()) as send,
			patch.object(frappe.db, "commit"),
		):
			self.assertEqual(_revoke(self.identity, self.body), {"revoked": 1})
			with self.assertRaises(MobileError) as raised:
				_register(self.identity, {"installation_id": str(uuid4())})
			self.assertEqual(raised.exception.code, "mobile_session_revoked")
			send.assert_not_called()
			for call in list(after_commit.add.call_args_list):
				call.args[0]()
			send.assert_called_once_with((self.sid,))
			from platform_core.mobil.sessions import is_session_closure_pending

			self.assertFalse(is_session_closure_pending(self.sid))

	def test_manager_can_retry_remote_closure_of_an_already_revoked_installation(self):
		from platform_core.api.mobile import _register, _revoke
		from platform_core.mobil import ai_tools

		_register(self.identity, self.body)
		with (
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch("platform_core.mobil.sessions.send_session_revocations", return_value=(self.sid,)) as send,
		):
			_revoke(self.identity, self.body)
			for call in list(after_commit.add.call_args_list):
				call.args[0]()
			send.assert_called_once_with((self.sid,))
			after_commit.reset_mock()
			plan = ai_tools.prepare_revoke_installation(self.body["installation_id"])
			self.assertEqual(ai_tools.execute_revocation(plan)["revoked"], 0)
			for call in list(after_commit.add.call_args_list):
				call.args[0]()
			self.assertEqual(send.call_count, 2)

	def test_legacy_installation_gets_sid_on_explicit_registration(self):
		from platform_core.api.mobile import _register
		from platform_core.mobil.store import MobileStore

		legacy = SimpleNamespace(account=self.account, scope="mobile", principal="fixture")
		MobileStore().install(legacy, self.body["installation_id"])
		_register(self.identity, self.body)
		self.assertEqual(
			frappe.db.get_value("Mobile Installation", self.body["installation_id"], "session_id"), self.sid
		)

	def test_only_explicit_activity_updates_last_user_activity(self):
		from platform_core.api.mobile import _activity, _push, _register

		_register(self.identity, self.body)
		state = "Mobile Account State"
		self.assertIsNone(frappe.db.get_value(state, self.account, "last_user_activity_at"))
		with patch("platform_core.api.mobile.push", return_value={}):
			_push(self.identity, {**self.body, "operations": []})
		self.assertIsNone(frappe.db.get_value(state, self.account, "last_user_activity_at"))
		with patch("platform_core.api.mobile.time.time", return_value=1700000000):
			_activity(self.identity, self.body)
		self.assertEqual(frappe.db.get_value(state, self.account, "last_user_activity_at"), "1700000000")
		with patch("platform_core.api.mobile.push", return_value={}):
			_push(self.identity, {**self.body, "operations": []})
		self.assertEqual(frappe.db.get_value(state, self.account, "last_user_activity_at"), "1700000000")
