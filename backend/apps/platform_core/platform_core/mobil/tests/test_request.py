"""Exercise the real mobile request boundary with isolated Frappe state."""

import json
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
					"installation": "12345678-1234-4234-8234-123456789abc",
					"issuer": "fixture",
					"subject": "fixture-user",
					"iat": self.issued_at,
					"auth_time": self.issued_at - 10,
					"sid": "session-01",
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
		patch("platform_core.mobil.store.frappe", self.frappe).start()
		patch.object(request, "_limit_and_count").start()
		self.revoked = patch.object(request, "is_session_revoked", return_value=False, create=True).start()

	def assert_rejected(self, code, status):
		with self.assertRaises(MobileError) as raised:
			request.mobile_request("v1_register")
		self.assertEqual((raised.exception.code, raised.exception.status), (code, status))

	def test_contract_identity_accepts_six_fields_and_binds_the_installation(self):
		claims = self.frappe.local.mobile_identity
		for key in ("issuer", "subject", "iat"):
			del claims[key]
		self.frappe.db.get_value.return_value = ("fixture", "fixture-user")
		self.request.get_data.return_value = json.dumps({"installation_id": claims["installation"]}).encode()
		identity, _unused = request.mobile_request("v1_register")
		self.assertEqual(identity.installation, claims["installation"])
		self.assertEqual(identity.subject, "fixture-user")
		self.assertIsNone(identity.issued_at)
		self.request.get_data.return_value = b'{"installation_id":"12345678-1234-4234-8234-123456789abd"}'
		self.assert_rejected("installation_unavailable", 403)
		self.request.path = "/api/method/platform_core.api.mobile.v1_revoke"
		_unused, body = request.mobile_request("v1_revoke")
		self.assertNotEqual(body["installation_id"], claims["installation"])
		self.request.path = "/api/method/platform_core.api.mobile.v1_register"
		claims.pop("installation")
		self.assert_rejected("mobile_token_required", 401)

	def test_verified_issued_at_is_required_and_propagated(self):
		identity, _unused = request.mobile_request("v1_register")
		self.assertEqual(identity.issued_at, self.issued_at)
		for invalid in (None, True, -1, self.issued_at + 3600):
			with self.subTest(invalid=invalid):
				self.frappe.local.mobile_identity["iat"] = invalid
				self.assert_rejected("mobile_token_required", 401)

	def test_sid_matches_identity_sync_contract(self):
		for invalid in ("has.dot", "has~tilde", "x" * 129):
			with patch.dict(self.frappe.local.mobile_identity, {"sid": invalid}):
				self.assert_rejected("mobile_token_required", 401)

	def test_verified_auth_time_is_required_and_propagated(self):
		identity, _unused = request.mobile_request("v1_register")
		self.assertEqual(identity.auth_time, self.issued_at - 10)
		for invalid in (None, True, 0, "123", self.issued_at + 3600):
			with patch.dict(self.frappe.local.mobile_identity, {"auth_time": invalid}):
				with self.assertRaisesRegex(MobileError, "mobile_token_required"):
					request.mobile_request("v1_register")

	def test_mobile_identity_requires_sid_and_rejects_revoked_session(self):
		identity, _unused = request.mobile_request("v1_register")
		self.assertEqual(identity.sid, "session-01")
		for sid in (None, "", "bad\nsid", "x" * 141):
			with self.subTest(sid=sid), patch.dict(self.frappe.local.mobile_identity, {"sid": sid}):
				self.assert_rejected("mobile_token_required", 401)
		self.revoked.return_value = True
		self.assert_rejected("mobile_session_revoked", 401)

	def test_issued_at_allows_thirty_seconds_of_clock_skew(self):
		with patch.object(request.time, "time", return_value=self.issued_at):
			self.frappe.local.mobile_identity["iat"] = self.issued_at + 30
			identity, _unused = request.mobile_request("v1_register")
			self.assertEqual(identity.issued_at, self.issued_at + 30)
			self.frappe.local.mobile_identity["iat"] += 1
			self.assert_rejected("mobile_token_required", 401)

	def test_empty_query_cmd_and_noncanonical_route_are_rejected(self):
		self.request.args = {"cmd": ""}
		self.assert_rejected("invalid_mobile_route", 400)
		self.request.args = {}
		self.request.path += "/"
		self.assert_rejected("invalid_mobile_route", 400)

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
		self.assertEqual(self.frappe.local.response["http_status_code"], 503)
		self.assertEqual(self.frappe.local.response["code"], "mobile_busy")
		self.assertEqual(self.frappe.local.response_headers, {"Retry-After": "1"})

	def test_deadlocks_wait_after_rollbacks_only_between_attempts(self):
		action = Mock(side_effect=Deadlock())
		with patch.object(request.time, "sleep") as sleep:
			request.endpoint_response("v1_register", action)
		self.assertEqual(sleep.call_count, 2)
		self.assertTrue(all(0 < call.args[0] <= 0.24 for call in sleep.call_args_list))

	def test_exhausted_deadlocks_return_retry_after(self):
		action = Mock(side_effect=Deadlock())
		self.assertIsNone(request.endpoint_response("v1_register", action))
		self.assertEqual(action.call_count, 3)
		self.assertEqual(self.frappe.local.response["http_status_code"], 503)
		self.assertEqual(self.frappe.local.response_headers, {"Retry-After": "1"})

	def test_pwa_requires_matching_cookie_origin_and_csrf(self):
		self.request.path = "/api/method/platform_core.api.mobile_pwa.v1_pull"
		self.request.host_url = "http://test-mobile.localhost/"
		self.frappe.conf = {"host_name": "https://test-mobile.localhost"}
		self.frappe.db.get_value.return_value = ("fixture", "fixture-user")
		self.request.cookies = {"sid": "cookie-session"}
		self.request.headers.pop("Authorization")
		self.request.headers.update(
			{"Origin": "https://test-mobile.localhost", "X-Frappe-CSRF-Token": "csrf-token"}
		)
		self.frappe.local.login_manager.user = self.frappe.session.user
		self.frappe.session.sid = "cookie-session"
		self.frappe.session.data = SimpleNamespace(csrf_token="csrf-token", creation="2026-11-22 07:00:00")
		with (
			patch.object(request, "_limit_and_count"),
			patch.object(request, "get_system_timezone", return_value="UTC", create=True),
		):
			identity, body = request.pwa_request("v1_pull")
			self.assertEqual((identity.scope, identity.sid, body), ("pwa", None, {}))
			self.assertEqual(identity.principal, request.content_digest(["fixture", "fixture-user"]))
			with patch.object(self.frappe.db.get_value, "return_value", None):
				with self.assertRaises(MobileError):
					request.pwa_request("v1_pull")
			for header, invalid in (
				("Origin", "https://other.example.test"),
				("X-Frappe-CSRF-Token", ""),
				("X-Frappe-CSRF-Token", "wrong"),
				("Authorization", "Bearer unrelated"),
			):
				with self.subTest(header=header), patch.dict(self.request.headers, {header: invalid}):
					with self.assertRaises(MobileError):
						request.pwa_request("v1_pull")
			self.request.cookies["sid"] = "other-session"
			with self.assertRaises(MobileError):
				request.pwa_request("v1_pull")

	def test_pwa_background_request_does_not_schedule_session_refresh(self):
		session = Mock()
		self.frappe.local.session_obj = session
		with (
			patch.object(request, "pwa_request", return_value=(Mock(), {})),
			patch.object(request, "run_transaction", return_value={}),
		):
			request.pwa_endpoint_response("v1_pull", Mock())
			self.assertIsNone(self.frappe.local.session_obj)
			self.frappe.local.session_obj = session
			request.pwa_endpoint_response("v1_activity", Mock())
			self.assertIs(self.frappe.local.session_obj, session)

	def test_mobile_responses_include_server_time(self):
		with patch.object(request.time, "time", return_value=self.issued_at + 1):
			self.assertEqual(request.endpoint_response("v1_register", Mock(return_value={})), {})
			self.assertEqual(self.frappe.local.response["server_time"], self.issued_at + 1)
			self.frappe.local.response.clear()
			self.request.headers.pop("Authorization")
			self.assertIsNone(request.endpoint_response("v1_register", Mock()))
			self.assertEqual(self.frappe.local.response["server_time"], self.issued_at + 1)
