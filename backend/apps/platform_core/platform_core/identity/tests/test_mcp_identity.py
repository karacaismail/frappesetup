"""MCP identity acceptance (decision 0017), with real signed tokens and no external calls."""

import json
import time
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

import frappe
from urllib3.exceptions import ConnectTimeoutError

from platform_core.identity import api
from platform_core.identity.exceptions import KeycloakKeysUnavailable, ServiceTokenRejected
from platform_core.identity.tests import helpers

RESOURCE = "https://tenant.example.test/api/method/platform_core.api.ai.mcp"
ISSUER = "https://identity.example.test/realms/platform"
CLIENT = "mcp-client"
SUBJECT = "sample-subject"
SID = "11111111-1111-4111-8111-111111111111"
ACCOUNT = "sample-user@example.test"
INTROSPECTION_URL = ISSUER + "/protocol/openid-connect/token/introspect"


class TestMcpIdentity(TestCase):
	def setUp(self):
		self.conf = {
			"mcp_oauth_enabled": 1,
			"mcp_oauth_resource": RESOURCE,
			"mcp_oauth_client_ids": [CLIENT],
			"mcp_oauth_introspection_secret": "test-only",
			"keycloak_public_url": "https://identity.example.test",
			"keycloak_realm": "platform",
			"kimlik_deletion_hmac_key": "synthetic",
		}
		self.db = Mock()
		self.db.exists.return_value = False
		self.db.get_value.side_effect = [ACCOUNT, 1]
		self.enterContext(patch.object(frappe, "conf", self.conf))
		self.enterContext(patch.object(frappe, "db", self.db))
		self.enterContext(patch.object(frappe, "_", side_effect=lambda message, **kwargs: message))
		self.set_user = self.enterContext(patch.object(frappe, "set_user"))
		self.enterContext(helpers.jwks_patch())
		self.transport = self.enterContext(patch("urllib3.PoolManager.request"))
		self.reply = MagicMock()
		self.transport.return_value.__enter__.return_value = self.reply
		self.reply.status = 200
		self.reply.read.return_value = json.dumps(
			{"active": True, "client_id": CLIENT, "sub": SUBJECT, "sid": SID, "username": "sample-user"}
		).encode()

	def claims(self, **overrides):
		now = int(time.time())
		return helpers.access_payload(
			**{
				"iss": ISSUER,
				"sub": SUBJECT,
				"aud": RESOURCE,
				"azp": CLIENT,
				"scope": "openid mcp",
				"sid": SID,
				"iat": now - 1,
				"exp": now + 299,
				**overrides,
			},
		)

	def check_rejected(self, claims=None, *, token=None, reason=None):
		if token is None:
			token = helpers.key().sign(claims or self.claims())
		with self.assertRaises(ServiceTokenRejected) as denied:
			api.verify_mcp_token(token)
		self.assertEqual(denied.exception.http_status_code, 401)
		self.assertEqual(str(denied.exception), "MCP token rejected.")
		if reason is not None:
			self.assertEqual(denied.exception.reason, reason)

	def test_config_needs_explicit_switch_and_safe_complete_settings(self):
		self.assertEqual(api.mcp_oauth_config(), {"resource": RESOURCE, "issuer": ISSUER})
		for field, value in (
			("mcp_oauth_enabled", 0),
			("mcp_oauth_enabled", "false"),
			("mcp_oauth_resource", RESOURCE.replace("https:", "http:")),
			("mcp_oauth_resource", RESOURCE + "?wrong=yes"),
			("mcp_oauth_resource", RESOURCE.replace("tenant.", 'tenant."')),
			(
				"mcp_oauth_resource",
				RESOURCE.replace("tenant.example.test", "evil.example.test@tenant.example.test"),
			),
			("keycloak_public_url", "https://identity.example.test#"),
			("keycloak_internal_url", "http://identity.example.test"),
			("mcp_oauth_client_ids", []),
			("mcp_oauth_introspection_secret", ""),
		):
			with self.subTest(field=field, value=value), patch.dict(self.conf, {field: value}):
				self.assertIsNone(api.mcp_oauth_config())
				self.check_rejected()

	def test_valid_signed_token_resolves_live_identity_without_setting_user(self):
		claims = self.claims()
		result = api.verify_mcp_token(helpers.key().sign(claims))
		self.assertEqual(
			result,
			{
				"account": ACCOUNT,
				"issuer": ISSUER,
				"subject": SUBJECT,
				"session_id": SID,
				"resource": RESOURCE,
				"client_id": CLIENT,
				"issued_at": claims["iat"],
				"expires_at": claims["exp"],
				"scopes": ["openid", "mcp"],
			},
		)
		self.set_user.assert_not_called()
		method, url = self.transport.call_args.args
		self.assertEqual((method, url), ("POST", INTROSPECTION_URL))
		self.assertIs(self.transport.call_args.kwargs["redirect"], False)
		self.assertIs(self.transport.call_args.kwargs["retries"], False)
		self.assertEqual(
			self.db.get_value.call_args_list[0].args,
			("PLT Identity Link", {"issuer": ISSUER, "subject": SUBJECT}, "user"),
		)

	def test_rejects_bad_signature_algorithm_and_authority_claims_before_introspection(self):
		wrong_key = helpers.Key()
		self.check_rejected(token=wrong_key.sign(self.claims(), kid=helpers.key().kid))
		self.check_rejected(token=helpers.key().sign(self.claims(), alg="none"))
		for changes in (
			{"iss": "https://wrong.example.test/realms/platform"},
			{"aud": RESOURCE + "/wrong"},
			{"aud": [RESOURCE, RESOURCE + "/another-site"]},
			{"azp": "another-client"},
			{"scope": "openid mobile"},
			{"scope": "openid\tmcp"},
			{"scope": "mcp offline_access"},
			{"sid": None},
			{"sid": SID + "\n"},
			{"sub": None},
			{"typ": "ID"},
		):
			with self.subTest(changes=changes):
				self.check_rejected(self.claims(**changes))
		self.assertEqual(self.transport.call_count, 0)

	def test_rejects_non_integer_expiry_and_invalid_lifetimes(self):
		now = int(time.time())
		for changes in (
			{"exp": now + 99.5},
			{"iat": now - 1.5},
			{"iat": True},
			{"iat": None},
			{"iat": now + 30},
			{"iat": now - 3, "exp": now + 300},
		):
			with self.subTest(changes=changes):
				self.check_rejected(self.claims(**changes))
		self.check_rejected(self.claims(iat=now - 100, exp=now - 1), reason="expired")
		self.assertEqual(self.transport.call_count, 0)

	def test_rejects_deleted_disabled_unlinked_and_builtin_accounts(self):
		for deleted, values in (
			(True, [ACCOUNT, 1]),
			(False, [ACCOUNT, 0]),
			(False, [None]),
			(False, ["Administrator", 1]),
			(False, ["Guest", 1]),
		):
			with self.subTest(deleted=deleted, values=values):
				self.db.exists.return_value = deleted
				self.db.get_value.side_effect = values
				self.check_rejected()
		self.assertEqual(self.transport.call_count, 0)

	def test_checks_session_on_each_request_and_rejects_after_logout(self):
		token = helpers.key().sign(self.claims())
		self.db.get_value.side_effect = [ACCOUNT, 1] * 2
		self.assertEqual(api.verify_mcp_token(token)["account"], ACCOUNT)
		self.reply.read.return_value = b'{"active":false}'
		self.check_rejected(token=token)
		self.assertEqual(self.transport.call_count, 2)

	def test_rejects_introspection_of_wrong_session_subject_client_or_service_account(self):
		active = {"active": True, "client_id": CLIENT, "sub": SUBJECT, "sid": SID, "username": "sample-user"}
		for field, value in (
			("sid", "wrong-sid"),
			("sub", "wrong-subject"),
			("client_id", "other-client"),
			("username", "service-account-mcp-client"),
			("username", None),
		):
			with self.subTest(field=field):
				self.db.get_value.side_effect = [ACCOUNT, 1]
				self.reply.read.return_value = json.dumps({**active, field: value}).encode()
				self.check_rejected()

	def test_provider_outage_has_fixed_status_and_message(self):
		token = helpers.key().sign(self.claims())
		for status, body in ((301, b""), (503, b""), (200, b"invalid"), (200, b"{}")):
			with self.subTest(status=status):
				self.db.get_value.side_effect = [ACCOUNT, 1]
				self.reply.status = status
				self.reply.read.return_value = body
				with self.assertRaises(KeycloakKeysUnavailable) as unavailable:
					api.verify_mcp_token(token)
				self.assertEqual(unavailable.exception.http_status_code, 503)
				self.assertTrue(unavailable.exception.skip_error_log)
				self.assertEqual(str(unavailable.exception), "MCP identity provider unavailable.")
		self.db.get_value.side_effect = [ACCOUNT, 1]
		self.transport.side_effect = ConnectTimeoutError("simulated")
		with self.assertRaises(KeycloakKeysUnavailable):
			api.verify_mcp_token(token)
		with helpers.jwks_unavailable_patch(), self.assertRaises(KeycloakKeysUnavailable):
			api.verify_mcp_token(token)
