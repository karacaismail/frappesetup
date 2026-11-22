"""Verify identity-sync account revocation and repeatability against Frappe."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.mobil import lifecycle
from platform_core.mobil.store import MobileStore


class ServiceRevocationTest(IntegrationTestCase):
	def setUp(self):
		self.account = (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": f"service-mobile-{uuid4().hex}@example.test",
					"first_name": "Mobile Test",
					"send_welcome_email": 0,
					"enabled": 0,
				}
			)
			.insert()
			.name
		)
		self.issuer = "https://identity.example.test/realms/platform"
		self.subject = str(uuid4())
		self.request = Mock(
			path="/api/method/platform_core.api.mobile.revoke_user_installations",
			args={},
			cookies={},
			is_json=True,
			content_length=None,
			headers={"Authorization": "Bearer synthetic-service"},
		)
		self.request.get_data.return_value = json.dumps(
			{"issuer": self.issuer, "subject": self.subject}
		).encode()
		self.enterContext(patch.object(frappe.local, "request", self.request, create=True))
		self.enterContext(
			patch.object(frappe.local, "login_manager", SimpleNamespace(user="Guest"), create=True)
		)
		self.enterContext(patch.object(frappe.local, "response", {}, create=True))
		self.enterContext(patch.object(frappe.local, "response_headers", {}, create=True))
		self.enterContext(
			patch.object(
				frappe.local,
				"kimlik_service_claims",
				{"azp": "identity-sync", "iss": self.issuer},
				create=True,
			)
		)

	def test_service_deletes_notification_bindings_and_replays_result(self):
		from platform_core.api.mobile import revoke_user_installations

		identity = SimpleNamespace(
			account=self.account, scope="mobile", principal="fixture", sid=str(uuid4())
		)
		installation = str(uuid4())
		MobileStore().install(identity, installation)
		frappe.db.set_value("Mobile Installation", installation, "notification_token", "synthetic-binding")
		with patch("platform_core.api.mobile._linked_account", return_value=self.account):
			result = revoke_user_installations()
			self.assertEqual(result, {"revoked": 1})
			first_cutoff = lifecycle._account_state(self.account).revoked_through
			row = frappe.db.get_value(
				"Mobile Installation", installation, ["revoked", "notification_token"], as_dict=True
			)
			self.assertTrue(row.revoked)
			self.assertFalse(row.notification_token)
			self.assertEqual(revoke_user_installations(), result)
			self.assertEqual(lifecycle._account_state(self.account).revoked_through, first_cutoff)

	def test_repeat_retries_pending_closure_but_never_resends_confirmed_closure(self):
		from platform_core.api.mobile import revoke_user_installations

		sid = str(uuid4())
		identity = SimpleNamespace(account=self.account, scope="mobile", principal="fixture", sid=sid)
		MobileStore().install(identity, str(uuid4()))
		with (
			patch("platform_core.api.mobile._linked_account", return_value=self.account),
			patch("platform_core.mobil.sessions.send_session_revocations", side_effect=[(sid,), ()]) as send,
			patch.object(frappe.db, "after_commit", Mock()) as after_commit,
			patch.object(frappe.db, "commit"),
		):
			for call_number in range(3):
				self.assertEqual(revoke_user_installations(), {"revoked": 1})
				for callback in list(after_commit.add.call_args_list):
					callback.args[0]()
				after_commit.reset_mock()
				self.assertEqual(send.call_count, min(call_number + 1, 2))

	def test_no_identity_link_returns_404_without_creating_state(self):
		from platform_core.api.mobile import revoke_user_installations

		with patch("platform_core.api.mobile._linked_account", return_value=None):
			self.assertIsNone(revoke_user_installations())
		self.assertEqual(frappe.local.response["http_status_code"], 404)
		self.assertEqual(frappe.local.response["code"], "IdentityNotFound")
		self.assertEqual(frappe.local.response["exc_type"], "IdentityNotFound")
		self.assertIsNone(lifecycle._account_state(self.account))

	def test_wrong_azp_or_browser_cookie_does_not_reach_identity_lookup(self):
		from platform_core.api.mobile import revoke_user_installations

		with patch("platform_core.api.mobile._linked_account") as lookup:
			frappe.local.kimlik_service_claims["azp"] = "different-service"
			self.assertIsNone(revoke_user_installations())
			self.assertEqual(frappe.local.response["http_status_code"], 403)
			frappe.local.kimlik_service_claims["azp"] = "identity-sync"
			self.request.cookies = {"sid": "browser-session"}
			frappe.local.login_manager.user = self.account
			self.assertIsNone(revoke_user_installations())
			self.assertEqual(frappe.local.response["http_status_code"], 403)
			lookup.assert_not_called()
