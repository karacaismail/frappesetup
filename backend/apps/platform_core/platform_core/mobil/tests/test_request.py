"""Exercise the real mobile request boundary with isolated Frappe state."""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from platform_core.mobil.protocol import MobileError

try:
	from platform_core.mobil import request
except ModuleNotFoundError as error:
	if error.name != "frappe":
		raise
	raise unittest.SkipTest("Frappe is required for request boundary tests") from error


class Deadlock(Exception):
	pass


class Timeout(Exception):
	pass


class MobileRequestTest(unittest.TestCase):
	def setUp(self):
		self.issued_at = int(time.time()) - 1
		self.request = Mock(
			path="/api/method/platform_core.api.mobile.v1_register",
			args={},
			cookies={},
			content_length=None,
			is_json=True,
			headers={
				"Authorization": "Bearer synthetic",
				"X-Mobile-App-Version": "1.0.0",
				"X-Mobile-Contract-Version": "1",
			},
		)
		self.request.get_data.return_value = b"{}"
		self.frappe = SimpleNamespace(
			local=SimpleNamespace(
				request=self.request,
				site="test-mobile.localhost",
				login_manager=SimpleNamespace(user="Guest"),
				mobile_identity={
					"site": "test-mobile.localhost",
					"account": "test@example.test",
					"scope": "mobile",
					"issuer": "fixture",
					"subject": "fixture-user",
					"iat": self.issued_at,
				},
				response={},
				response_headers={},
			),
			session=SimpleNamespace(user="test@example.test"),
			db=Mock(),
			QueryDeadlockError=Deadlock,
			QueryTimeoutError=Timeout,
		)
		self.addCleanup(patch.stopall)
		patch.object(request, "frappe", self.frappe).start()
		patch.object(request, "_limit_and_count").start()

	def assert_rejected(self, code, status):
		with self.assertRaises(MobileError) as raised:
			request.mobile_request("v1_register")
		self.assertEqual((raised.exception.code, raised.exception.status), (code, status))

	def test_verified_issued_at_is_required_and_propagated(self):
		identity, _ = request.mobile_request("v1_register")
		self.assertEqual(identity.issued_at, self.issued_at)
		for invalid in (None, True, -1, self.issued_at + 3600):
			with self.subTest(invalid=invalid):
				self.frappe.local.mobile_identity["iat"] = invalid
				self.assert_rejected("mobile_token_required", 401)

	def test_cookie_login_is_rejected_even_with_verified_identity(self):
		self.request.cookies = {"sid": "fake-session"}
		self.frappe.local.login_manager.user = self.frappe.session.user
		self.assert_rejected("mixed_authentication", 400)

	def test_identity_scope_site_and_account_mismatches_are_rejected(self):
		for key, value in (("site", "other.localhost"), ("scope", "web"), ("account", "other@example.test")):
			with self.subTest(key=key), patch.dict(self.frappe.local.mobile_identity, {key: value}):
				self.assert_rejected("mobile_token_required", 401)

	def test_body_cmd_is_rejected(self):
		self.request.get_data.return_value = b'{"cmd":""}'
		self.assert_rejected("invalid_mobile_route", 400)

	def test_duplicate_json_key_is_rejected(self):
		self.request.get_data.return_value = b'{"key":1,"key":2}'
		self.assert_rejected("invalid_json", 400)

	def test_non_json_is_rejected(self):
		self.request.is_json = False
		self.assert_rejected("json_required", 415)

	def test_deadlocked_action_is_retried(self):
		action = Mock(side_effect=[Deadlock(), {"ok": True}])
		self.assertEqual(request.endpoint_response("v1_register", action), {"ok": True})
		self.frappe.db.rollback.assert_called_once()

	def test_timeout_returns_retry_after_without_repeating_the_wait(self):
		action = Mock(side_effect=Timeout())
		self.assertIsNone(request.endpoint_response("v1_register", action))
		action.assert_called_once()
		self.assertEqual(self.frappe.local.response, {"http_status_code": 503, "code": "mobile_busy"})
		self.assertEqual(self.frappe.local.response_headers, {"Retry-After": "1"})

	def test_exhausted_deadlocks_return_retry_after(self):
		action = Mock(side_effect=Deadlock())
		self.assertIsNone(request.endpoint_response("v1_register", action))
		self.assertEqual(action.call_count, 3)
		self.assertEqual(self.frappe.local.response["http_status_code"], 503)
		self.assertEqual(self.frappe.local.response_headers, {"Retry-After": "1"})
