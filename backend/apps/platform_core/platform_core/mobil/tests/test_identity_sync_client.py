import json
from io import BytesIO
from logging import Logger
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from uuid import uuid4

from platform_core.kimlik import service_client
from platform_core.mobil import identity_sync_client as client


class IdentitySyncClientTest(TestCase):
	def setUp(self):
		self.addCleanup(patch.stopall)
		self.conf = {
			"mobile_identity_sync_url": "https://sync.example.test/",
			"keycloak_public_url": "https://id.example.test",
			"keycloak_realm": "platform",
			"keycloak_client_id": "site-kiraci1",
			"keycloak_client_secret": uuid4().hex,
			"keycloak_service_client_id": "site-kiraci1-service",
			"keycloak_service_client_secret": uuid4().hex,
		}
		patch.object(client.frappe, "conf", self.conf).start()
		patch.object(service_client, "_cached_bearer", None).start()
		self.logger = patch.object(client.frappe, "logger").start().return_value
		self.open = patch.object(client._OPENER, "open").start()
		patch.object(service_client._OPENER, "open", self.open).start()

	@staticmethod
	def response(body=b"", status=200):
		response = Mock(status=status)
		response.__enter__ = Mock(return_value=response)
		response.__exit__ = Mock(return_value=False)
		response.read.return_value = body
		return response

	def test_fetches_service_bearer_and_posts_to_exact_endpoint(self):
		self.open.side_effect = [self.response(b'{"access_token":"fixture-bearer"}'), self.response()]
		self.assertEqual(client.send_session_revocations([("session-fixture", "keycloak-fixture")] * 2), ())
		token, revoke = [call.args[0] for call in self.open.call_args_list]
		self.assertEqual(
			token.full_url, "https://id.example.test/realms/platform/protocol/openid-connect/token"
		)
		self.assertEqual(token.get_method(), "POST")
		self.assertEqual(
			parse_qs(token.data.decode()),
			{
				"grant_type": ["client_credentials"],
				"client_id": ["site-kiraci1-service"],
				"client_secret": [self.conf["keycloak_service_client_secret"]],
				"scope": ["aud-identity-sync"],
			},
		)
		self.assertEqual(revoke.full_url, "https://sync.example.test/v1/sessions/revoke")
		self.assertEqual(revoke.get_method(), "POST")
		self.assertEqual(revoke.get_header("Authorization"), "Bearer fixture-bearer")
		self.assertEqual(json.loads(revoke.data), {"sid": "session-fixture", "subject": "keycloak-fixture"})
		self.assertTrue(all(call.kwargs["timeout"] > 0 for call in self.open.call_args_list))
		self.logger.warning.assert_not_called()

	def test_one_failure_does_not_stop_the_batch_or_log_sensitive_values(self):
		self.open.side_effect = [
			self.response(b'{"access_token":"fixture-bearer"}'),
			URLError("private-session fixture-bearer fixture-secret"),
			self.response(),
		]
		self.assertEqual(
			client.send_session_revocations(
				[("private-session", "subject-one"), ("other-session", "subject-two")]
			),
			(("private-session", "subject-one"),),
		)
		self.assertEqual(self.open.call_count, 3)
		self.logger.warning.assert_called_once()
		for sensitive in ("private-session", "fixture-bearer", self.conf["keycloak_service_client_secret"]):
			self.assertNotIn(sensitive, str(self.logger.warning.call_args))

	def test_forbidden_closure_is_logged_and_is_not_retried(self):
		forbidden = ("private-session", "private-subject")
		retryable = ("unavailable-session", "unavailable-subject")
		error = HTTPError(
			"https://sync.example.test/v1/sessions/revoke",
			403,
			"private-session private-subject fixture-bearer fixture-secret",
			None,
			BytesIO(b"private response body"),
		)
		self.open.side_effect = [
			self.response(b'{"access_token":"fixture-bearer"}'),
			error,
			self.response(status=503),
			self.response(),
		]

		self.assertEqual(
			client.send_session_revocations([forbidden, retryable, ("closed", "subject")]), (retryable,)
		)
		self.assertEqual(self.open.call_count, 4)
		self.logger.error.assert_called_once()
		self.assertIn("403", str(self.logger.error.call_args))
		self.assertTrue(error.fp.closed)
		for value in (
			*forbidden,
			"fixture-bearer",
			self.conf["keycloak_service_client_secret"],
			"private response body",
		):
			self.assertNotIn(value, str(self.logger.mock_calls))

	def test_forbidden_closure_log_has_only_fixed_text(self):
		session = ("fixture-private-sid", "person@example.test")
		refusal = HTTPError(
			"https://sync.example.test/v1/sessions/revoke",
			403,
			"person@example.test fixture-private-sid fixture-private-bearer",
			{"X-Fixture-Secret": "fixture-private-header"},
			BytesIO(b"fixture-private-body"),
		)
		self.open.side_effect = [self.response(b'{"access_token":"fixture-private-bearer"}'), refusal]
		logger = Logger("mobile_sessions")
		with (
			patch.object(client.frappe, "logger", return_value=logger),
			self.assertLogs(logger, "ERROR") as log,
		):
			self.assertEqual(client.send_session_revocations([session]), ())

		self.assertEqual(
			log.output,
			[
				"ERROR:mobile_sessions:Identity-sync refused mobile session closure (HTTP 403). "
				"Local revocation remains in effect."
			],
		)
		self.assertIsNone(log.records[0].exc_info)

	def test_unauthorized_closure_evicts_the_cached_bearer(self):
		target = ("session", "subject")
		self.open.side_effect = [
			self.response(b'{"access_token":"old-bearer","expires_in":60}'),
			self.response(status=401),
			self.response(b'{"access_token":"new-bearer","expires_in":60}'),
			self.response(),
		]
		self.assertEqual(client.send_session_revocations([target]), (target,))
		self.assertEqual(client.send_session_revocations([target]), ())
		self.assertEqual(self.open.call_args.args[0].get_header("Authorization"), "Bearer new-bearer")

	def test_reuses_service_bearer_until_expiry(self):
		self.open.side_effect = [
			self.response(b'{"access_token":"fixture-bearer","expires_in":60}'),
			self.response(),
			self.response(),
			self.response(b'{"access_token":"new-bearer","expires_in":60}'),
			self.response(),
		]
		with patch.object(service_client, "monotonic", return_value=100) as clock:
			self.assertEqual(client.send_session_revocations([("session-one", "keycloak-fixture")]), ())
			clock.return_value = 120
			self.assertEqual(client.send_session_revocations([("session-two", "keycloak-fixture")]), ())
			clock.return_value = 161
			self.assertEqual(client.send_session_revocations([("session-three", "keycloak-fixture")]), ())
		self.assertEqual(self.open.call_count, 5)

	def test_rejects_plaintext_and_credentials_in_configured_urls(self):
		for address in (
			"http://sync.example.test",
			"https://user:secret@sync.example.test",
			"//sync.example.test",
		):
			with self.subTest(address=address):
				self.conf["mobile_identity_sync_url"] = address
				self.assertEqual(
					client.send_session_revocations([("session", "keycloak-fixture")]),
					(("session", "keycloak-fixture"),),
				)
		self.open.assert_not_called()

	def test_browser_client_cannot_request_a_service_bearer(self):
		self.conf["keycloak_service_client_id"] = self.conf["keycloak_client_id"]
		self.assertEqual(client.send_session_revocations([("session", "subject")]), (("session", "subject"),))
		self.open.assert_not_called()

	def test_other_tenant_service_client_is_rejected(self):
		self.conf["keycloak_service_client_id"] = "site-kiraci2-service"
		self.assertEqual(client.send_session_revocations([("session", "subject")]), (("session", "subject"),))
		self.open.assert_not_called()

	def test_uses_the_internal_keycloak_https_address(self):
		self.conf["keycloak_internal_url"] = "https://keycloak.example.test/"
		self.open.side_effect = [self.response(b'{"access_token":"fixture-bearer"}'), self.response()]
		self.assertEqual(client.send_session_revocations([("session", "subject")]), ())
		self.assertEqual(
			self.open.call_args_list[0].args[0].full_url,
			"https://keycloak.example.test/realms/platform/protocol/openid-connect/token",
		)

	def test_missing_service_secret_does_not_use_the_browser_secret(self):
		del self.conf["keycloak_service_client_secret"]
		self.assertEqual(client.send_session_revocations([("session", "subject")]), (("session", "subject"),))
		self.open.assert_not_called()

	def test_empty_batch_does_not_need_configuration(self):
		self.conf.clear()
		self.assertEqual(client.send_session_revocations(()), ())
		self.open.assert_not_called()
		self.logger.warning.assert_not_called()

	def test_redirects_are_not_followed(self):
		self.assertIsNone(
			client._NoRedirect().redirect_request(
				None, None, 307, "Redirect", {}, "https://other.example.test"
			)
		)

	def test_invalid_token_avoids_dispatch(self):
		self.open.return_value = self.response(b'{"access_token":"bearer with spaces"}')
		self.assertEqual(
			client.send_session_revocations([("session", "keycloak-fixture")]),
			(("session", "keycloak-fixture"),),
		)
		self.open.assert_called_once()
