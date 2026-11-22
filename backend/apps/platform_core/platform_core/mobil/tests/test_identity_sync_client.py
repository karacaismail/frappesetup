from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import parse_qs

from platform_core.mobil import identity_sync_client as client


class IdentitySyncClientTest(TestCase):
	def setUp(self):
		self.addCleanup(patch.stopall)
		self.conf = {
			"mobile_identity_sync_url": "https://sync.example.test/",
			"mobile_identity_sync_token_url": "https://id.example.test/realms/platform/protocol/openid-connect/token",
			"mobile_identity_sync_client_id": "platform-core-fixture",
			"mobile_identity_sync_client_secret": "fixture-secret",
		}
		patch.object(client.frappe, "conf", self.conf).start()
		self.logger = patch.object(client.frappe, "logger").start().return_value
		self.open = patch.object(client._OPENER, "open").start()

	@staticmethod
	def response(body=b"", status=200):
		response = Mock(status=status)
		response.__enter__ = Mock(return_value=response)
		response.__exit__ = Mock(return_value=False)
		response.read.return_value = body
		return response

	def test_fetches_service_bearer_and_posts_to_exact_endpoint(self):
		self.open.side_effect = [self.response(b'{"access_token":"fixture-bearer"}'), self.response()]
		self.assertEqual(client.send_session_revocations(["session-fixture", "session-fixture"]), ())
		token, revoke = [call.args[0] for call in self.open.call_args_list]
		self.assertEqual(token.full_url, self.conf["mobile_identity_sync_token_url"])
		self.assertEqual(token.get_method(), "POST")
		self.assertEqual(
			parse_qs(token.data.decode()),
			{
				"grant_type": ["client_credentials"],
				"client_id": ["platform-core-fixture"],
				"client_secret": ["fixture-secret"],
				"scope": ["aud-identity-sync"],
			},
		)
		self.assertEqual(revoke.full_url, "https://sync.example.test/v1/sessions/revoke")
		self.assertEqual(revoke.get_method(), "POST")
		self.assertEqual(revoke.get_header("Authorization"), "Bearer fixture-bearer")
		self.assertEqual(revoke.data, b'{"sid": "session-fixture"}')
		self.assertTrue(all(call.kwargs["timeout"] > 0 for call in self.open.call_args_list))
		self.logger.warning.assert_not_called()

	def test_one_failure_does_not_stop_the_batch_or_log_sensitive_values(self):
		self.open.side_effect = [
			self.response(b'{"access_token":"fixture-bearer"}'),
			URLError("private-session fixture-bearer fixture-secret"),
			self.response(),
		]
		self.assertEqual(
			client.send_session_revocations(["private-session", "other-session"]), ("private-session",)
		)
		self.assertEqual(self.open.call_count, 3)
		self.logger.warning.assert_called_once()
		for sensitive in ("private-session", "fixture-bearer", "fixture-secret"):
			self.assertNotIn(sensitive, str(self.logger.warning.call_args))

	def test_rejects_plaintext_and_credentials_in_configured_urls(self):
		for address in (
			"http://sync.example.test",
			"https://user:secret@sync.example.test",
			"//sync.example.test",
		):
			with self.subTest(address=address):
				self.conf["mobile_identity_sync_url"] = address
				self.assertEqual(client.send_session_revocations(["session"]), ("session",))
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
		self.assertEqual(client.send_session_revocations(["session"]), ("session",))
		self.open.assert_called_once()
