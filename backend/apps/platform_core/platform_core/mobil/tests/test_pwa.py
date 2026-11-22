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
	def test_background_sync_does_not_extend_the_cookie_session(self):
		account = f"pwa-{uuid4().hex}@example.test"
		password = uuid4().hex
		frappe.get_doc(doctype="User", email=account, first_name="PWA", send_welcome_email=0).insert()
		update_password(account, password)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- WSGI uses a separate connection.
		client = get_test_client(use_cookies=True)
		site = frappe.local.site

		def post(operation, body, headers=None):
			path = f"/api/method/platform_core.api.mobile_pwa.{operation}"
			if operation == "login":
				path = "/api/method/login"
			return make_request(
				client.open,
				args=(),
				kwargs={"path": path, "method": "POST", "buffered": True, "json": body, "headers": headers or {}},
				site=site,
			)

		try:
			login = post("login", {"usr": account, "pwd": password})
			self.assertEqual(login.status_code, 200)
			sid = client.get_cookie("sid").value
			self.addCleanup(frappe.cache.hdel, "session", sid)
			session = frappe.cache.hget("session", sid)
			token = frappe.generate_hash()
			aged = now_datetime() - timedelta(minutes=20)
			session["data"]["csrf_token"] = token
			session["data"]["last_updated"] = aged
			frappe.cache.hset("session", sid, session)
			headers = {
				"Origin": "http://localhost",
				"X-Frappe-CSRF-Token": token,
				"X-Mobile-App-Version": "1.0.0",
				"X-Mobile-Contract-Version": "1",
			}
			body = {"installation_id": str(uuid4())}
			for csrf in ("", "wrong"):
				response = post("v1_register", body, {**headers, "X-Frappe-CSRF-Token": csrf})
				self.assertIn(response.status_code, (400, 403))
			with patch.object(Session, "update", autospec=True) as refresh:
				response = post("v1_register", body, headers)
				self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
				refresh.assert_not_called()
				response = post("v1_activity", body, headers)
				self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
				refresh.assert_called_once()
			current = frappe.cache.hget("session", sid)
			self.assertEqual(get_datetime(current["data"]["last_updated"]), aged)
			self.assertIsInstance(response.json["message"]["last_user_activity_at"], int)
		finally:
			frappe.db.rollback()
			frappe.delete_doc("User", account)
			frappe.db.commit()  # nosemgrep: frappe-request-commit -- WSGI committed the test writes.
