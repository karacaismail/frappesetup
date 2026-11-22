import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from oidc_verify import JwksUnavailable
from werkzeug.exceptions import Forbidden, ServiceUnavailable

from press_tr import api
from press_tr.api import auth, identity, maintenance
from press_tr.kimlik import oidc, request_policy, service, sessions


class RequestGuardsTest(unittest.TestCase):
	def test_guest_allowlist_matches_the_contract(self):
		targets = {
			"press_tr.api.auth.get_login_url": Mock(),
			"press_tr.api.auth.keycloak_callback": Mock(),
			"press_tr.api.keycloak_backchannel_logout": Mock(),
		}
		with patch.object(request_policy, "frappe") as facade:
			facade.get_attr.side_effect = targets.__getitem__
			facade.session.user = "Guest"
			self.assertEqual(request_policy.allowed_guest_targets(), {facade.ping, *targets.values()})
			facade.local.press_request_target = (Mock(), {})
			facade.throw.side_effect = Forbidden
			with self.assertRaises(Forbidden):
				request_policy.enforce_guest_allowlist()

	def test_native_password_recovery_cannot_be_enabled(self):
		with self.assertRaises(Forbidden):
			request_policy.block_native_login()

	def test_snapshot_reset_rejects_pending_writes(self):
		with patch.object(identity, "frappe") as facade:
			facade.db.transaction_writes = 1
			with self.assertRaises(RuntimeError):
				identity.reset_read_snapshot()
			facade.db.rollback.assert_not_called()

	def test_team_lock_refreshes_snapshot_before_lookup_and_lock(self):
		with patch.object(identity, "frappe") as facade:
			facade.db.transaction_writes = 0
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

	def test_logout_redacts_token_before_verification(self):
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

	def test_proxy_overwrites_forwarded_client_address(self):
		from pathlib import Path

		config = Path(__file__).with_name("forwarded-client.conf")
		directives = [line.strip() for line in config.read_text().splitlines() if not line.startswith("#")]
		self.assertEqual(directives, ["proxy_set_header X-Forwarded-For $remote_addr;"])

	def test_team_invitation_dispatch_is_denied_by_callable(self):
		from press.api.account import accept_team_invite
		from press.api.client import run_doc_method

		with patch.object(
			request_policy,
			"frappe",
			SimpleNamespace(form_dict={"dt": "Team", "method": "invite_team_member"}),
		):
			for target in (accept_team_invite, run_doc_method):
				with self.assertRaises(Forbidden):
					request_policy.block_team_invitation(target, {})

	def test_server_script_cannot_replace_an_allowed_python_target(self):
		with (
			patch.object(request_policy, "frappe") as facade,
			patch.object(request_policy, "get_server_script_map", return_value={"_api": {"ping": "fixture"}}),
			patch.object(request_policy, "get_attr") as resolve,
		):
			facade.override_whitelisted_method.side_effect = lambda name: name
			self.assertIsNone(request_policy.resolve_method("ping"))
			resolve.assert_not_called()

	def test_maintenance_skips_missing_and_active_mappings(self):
		with (
			patch.object(maintenance, "frappe") as facade,
			patch.object(maintenance, "get_expired_threshold", return_value="2026-11-22 00:00:00"),
		):

			class Disappeared(Exception):
				pass

			facade.DoesNotExistError = Disappeared
			active, expired, orphan = Mock(), Mock(), Mock()
			facade.get_all.return_value = ["gone", "active", "expired", "orphan"]
			facade.get_doc.side_effect = [Disappeared, active, expired, orphan]
			facade.db.get_value.side_effect = ["2026-11-22 01:00:00", "2026-11-21 23:00:00", None]
			self.assertEqual(maintenance.cleanup_expired_sessions(), {"removed": 2})
			facade.only_for.assert_called_once_with("System Manager")
			active.delete.assert_not_called()
			expired.delete.assert_called_once_with(ignore_permissions=True)
			orphan.delete.assert_called_once_with(ignore_permissions=True)
