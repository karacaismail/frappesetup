"""Exercise PWA cookie authentication through Frappe's HTTP application."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.sessions import Session
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_datetime, get_test_client, now_datetime
from frappe.utils.password import update_password


class MobilePwaTest(IntegrationTestCase):
	def setUp(self):
		self.site = frappe.local.site
		self.enterContext(
			patch(
				"platform_core.mobil.request._identity_link",
				side_effect=lambda account: ("https://identity.example.test", account),
			)
		)

	def tearDown(self):
		frappe.db.rollback()

	def post(self, client, operation, body, headers=None):
		path = f"/api/method/platform_core.api.mobile_pwa.{operation}"
		if operation == "login":
			path = "/api/method/login"
		return make_request(
			client.open,
			args=(),
			kwargs={"path": path, "method": "POST", "buffered": True, "json": body, "headers": headers or {}},
			site=self.site,
		)

	def login(self):
		account = f"pwa-{uuid4().hex}@example.test"
		password = uuid4().hex
		frappe.get_doc(doctype="User", email=account, first_name="PWA", send_welcome_email=0).insert()
		update_password(account, password)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- WSGI uses a separate connection.
		self.addCleanup(self.delete_account, account)
		client = get_test_client(use_cookies=True)
		login = self.post(client, "login", {"usr": account, "pwd": password})
		self.assertEqual(login.status_code, 200)
		sid = client.get_cookie("sid").value
		self.addCleanup(frappe.cache.hdel, "session", sid)
		session = frappe.cache.hget("session", sid)
		session["data"]["csrf_token"] = frappe.generate_hash()
		frappe.cache.hset("session", sid, session)
		headers = {
			"Origin": (frappe.conf.get("host_name") or "http://localhost").rstrip("/"),
			"X-Frappe-CSRF-Token": session["data"]["csrf_token"],
			"X-Mobile-App-Version": "1.0.0",
			"X-Mobile-Contract-Version": "1",
		}
		return client, sid, headers

	def delete_account(self, account):
		frappe.delete_doc("User", account)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- WSGI committed the test writes.

	def test_website_user_can_call_only_declared_mobile_cookie_methods(self):
		methods = {
			f"platform_core.api.mobile_pwa.v1_{name}"
			for name in (
				"activity",
				"list_installations",
				"pull",
				"push",
				"register",
				"revoke",
				"revoke_installation",
			)
		}
		configured = set(frappe.get_hooks("website_user_allowed_methods"))
		self.assertEqual({method for method in configured if ".api.mobile" in method}, methods)
		client, sid, headers = self.login()
		self.assertEqual(frappe.cache.hget("session", sid)["data"]["user_type"], "Website User")
		body = {"installation_id": str(uuid4())}
		response = self.post(client, "v1_register", body, headers)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(response.json["message"], body)
		for path in (
			"platform_core.api.mobile.v1_register",
			"platform_core.api.mobile.revoke_user_installations",
		):
			response = make_request(
				client.open,
				args=(),
				kwargs={"path": f"/api/method/{path}", "method": "POST", "json": body, "headers": headers},
				site=self.site,
			)
			self.assertIn(response.status_code, (401, 403))

	def test_background_sync_does_not_extend_the_cookie_session(self):
		client, sid, headers = self.login()
		session = frappe.cache.hget("session", sid)
		aged = now_datetime() - timedelta(minutes=20)
		session["data"]["last_updated"] = aged
		frappe.cache.hset("session", sid, session)
		body = {"installation_id": str(uuid4())}
		for csrf in ("", "wrong"):
			response = self.post(client, "v1_register", body, {**headers, "X-Frappe-CSRF-Token": csrf})
			self.assertIn(response.status_code, (400, 403))
		with patch.object(Session, "update", autospec=True) as refresh:
			response = self.post(client, "v1_register", body, headers)
			self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
			refresh.assert_not_called()
			response = self.post(client, "v1_activity", body, headers)
			self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
			refresh.assert_called_once()
		current = frappe.cache.hget("session", sid)
		self.assertEqual(get_datetime(current["data"]["last_updated"]), aged)
		self.assertIsInstance(response.json["message"]["last_user_activity_at"], int)
		self.assertIsInstance(response.json["server_time"], int)

	def guest_denied(self, operation):
		response = self.post(get_test_client(), operation, {"installation_id": str(uuid4())})
		self.assertIn(response.status_code, (401, 403))

	def foreign_data_denied(self, operation):
		owner, _, owner_headers = self.login()
		other, _, other_headers = self.login()
		body = {"installation_id": str(uuid4())}
		self.assertEqual(self.post(owner, "v1_register", body, owner_headers).status_code, 200)
		if operation == "v1_push":
			body["operations"] = []
		response = self.post(other, operation, body, other_headers)
		expected = 200 if operation == "v1_revoke" else 403
		self.assertEqual(response.status_code, expected, response.get_data(as_text=True))
		if operation == "v1_revoke":
			self.assertEqual(response.json["message"], {"revoked": 0})

	def test_v1_list_installations_guest_denied(self):
		self.guest_denied("v1_list_installations")

	def test_v1_list_installations_foreign_data_denied(self):
		owner, _, owner_headers = self.login()
		other, _, other_headers = self.login()
		body = {"installation_id": str(uuid4())}
		self.assertEqual(self.post(owner, "v1_register", body, owner_headers).status_code, 200)
		response = self.post(other, "v1_list_installations", {}, other_headers)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"]["installations"], [])

	def test_v1_revoke_installation_guest_denied(self):
		self.guest_denied("v1_revoke_installation")

	def test_v1_revoke_installation_foreign_data_denied(self):
		owner, _, headers = self.login()
		other, _, other_headers = self.login()
		body = {"installation_id": str(uuid4())}
		self.assertEqual(self.post(owner, "v1_register", body, headers).status_code, 200)
		result = self.post(other, "v1_revoke_installation", body, other_headers)
		self.assertEqual(result.status_code, 404)
		result = self.post(owner, "v1_revoke_installation", body, headers)
		self.assertEqual(result.status_code, 200)
		self.assertEqual(result.json["message"], {"revoked": 1})

	def test_v1_register_guest_denied(self):
		self.guest_denied("v1_register")

	def test_v1_register_foreign_data_denied(self):
		self.foreign_data_denied("v1_register")

	def test_v1_activity_guest_denied(self):
		self.guest_denied("v1_activity")

	def test_v1_activity_foreign_data_denied(self):
		self.foreign_data_denied("v1_activity")

	def test_v1_pull_guest_denied(self):
		self.guest_denied("v1_pull")

	def test_v1_pull_foreign_data_denied(self):
		self.foreign_data_denied("v1_pull")

	def test_v1_push_guest_denied(self):
		self.guest_denied("v1_push")

	def test_v1_push_foreign_data_denied(self):
		self.foreign_data_denied("v1_push")

	def test_v1_revoke_guest_denied(self):
		self.guest_denied("v1_revoke")

	def test_v1_revoke_foreign_data_denied(self):
		self.foreign_data_denied("v1_revoke")
