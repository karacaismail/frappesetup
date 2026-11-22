import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from oidc_verify import JwksUnavailable
from werkzeug.exceptions import Forbidden, ServiceUnavailable

from press_tr import api, hooks
from press_tr.api import auth, identity
from press_tr.press_identity import oidc, request_policy, service, sessions


class RequestGuardsTest(unittest.TestCase):
	def test_legacy_rpc_overrides_are_deny_handlers(self):
		closed = request_policy.CLOSED_METHODS | request_policy.SOCIAL_METHODS
		self.assertEqual(set(hooks.override_whitelisted_methods), closed)
		for handler in hooks.override_whitelisted_methods.values():
			self.assertEqual(handler, "press_tr.press_identity.request_policy.deny_legacy_method")
		with self.assertRaises(Forbidden):
			request_policy.deny_legacy_method()

	def test_rpc_method_is_extracted_from_each_prefix(self):
		for prefix in request_policy.API_PREFIXES:
			self.assertEqual(request_policy.rpc_method(prefix + "fixture.echo/metadata"), "fixture.echo")

	def test_native_recovery_is_off_unless_enabled_for_administrator(self):
		with patch.object(request_policy, "frappe") as facade:
			facade.request.path = "/api/method/login"
			facade.form_dict.get.return_value = "Administrator"
			for value in (False, None, "false", "0"):
				facade.conf.press_tr_allow_admin_password_login = value
				with self.assertRaises(Forbidden):
					request_policy.block_native_login()
			facade.conf.press_tr_allow_admin_password_login = True
			request_policy.block_native_login()
			facade.form_dict.get.return_value = "desk-user@example.test"
			with self.assertRaises(Forbidden):
				request_policy.block_native_login()

	def test_team_lock_refreshes_snapshot_before_lookup_and_lock(self):
		with patch.object(identity, "frappe") as facade:
			facade.db.get_value.return_value = "team"
			facade.get_doc.return_value.keycloak_org_id = "organization"
			self.assertIs(identity.lock_team("organization"), facade.get_doc.return_value)
			self.assertEqual(
				facade.mock_calls[:5],
				[
					call.db.rollback(),
					call.db.get_value("Team", {"keycloak_org_id": "organization"}, "name"),
					call.db.rollback(),
					call.db.get_value("Team", "team", "name", for_update=True),
					call.get_doc("Team", "team", for_update=True),
				],
			)

	def test_https_state_cookie_has_host_prefix(self):
		with patch.object(auth, "callback_url", return_value="https://press.example.test/api"):
			self.assertEqual(auth.state_cookie(), "__Host-press_tr_login")

	def test_unavailable_oidc_keys_and_missing_issuer_return_503(self):
		with (
			patch.object(oidc, "jwks_cache"),
			patch.object(oidc, "server_endpoint"),
			patch.object(oidc, "issuer"),
			self.assertRaises(ServiceUnavailable),
		):
			oidc.verify(Mock(side_effect=JwksUnavailable), "fixture")
		with patch.object(
			oidc,
			"frappe",
			SimpleNamespace(conf=SimpleNamespace(keycloak_public_url=None, keycloak_realm=None)),
		):
			with self.assertRaises(ServiceUnavailable):
				oidc.issuer()

	def test_local_logout_removes_only_current_session_mapping(self):
		with patch.object(sessions, "frappe") as facade:
			facade.session.user = "website@example.test"
			facade.session.sid = "current"
			facade.db.get_value.return_value = "identity"
			facade.get_all.return_value = ["old", "current"]
			old, current = Mock(), Mock()
			old.get_password.return_value = "old"
			current.get_password.return_value = "current"
			facade.get_doc.side_effect = [old, current]
			sessions.remove_mapping()
			old.delete.assert_not_called()
			current.delete.assert_called_once_with(ignore_permissions=True)

	def test_logout_redacts_token_before_calling_rate_limited_helper(self):
		form = {"logout_token": "fixture"}
		with (
			patch.object(api, "frappe", SimpleNamespace(form_dict=form)),
			patch.object(api, "_revoke_keycloak_sessions") as revoke,
		):

			def observe(token):
				self.assertNotIn("logout_token", form)
				self.assertEqual(token, "fixture")

			revoke.side_effect = observe
			api.keycloak_backchannel_logout("fixture")
			revoke.assert_called_once()

	def test_service_guard_rejects_a_resumed_user_session(self):
		with (
			patch.object(service, "frappe") as facade,
			patch.object(service, "reject", side_effect=Forbidden) as reject,
		):
			facade.request.path = "/api/method/press_tr.api.identity.ensure_team"
			facade.request.method = "POST"
			facade.form_dict = {}
			facade.request.cookies = {"sid": "current"}
			facade.local.session_obj = SimpleNamespace(sid="current", user="user@example.test")
			with self.assertRaises(Forbidden):
				service.authorize_identity_sync()
			reject.assert_called_once()
