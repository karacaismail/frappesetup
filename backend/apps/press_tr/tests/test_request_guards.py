import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import frappe
from oidc_verify import JwksUnavailable
from werkzeug.exceptions import Forbidden, ServiceUnavailable

from press_tr import api, hooks
from press_tr.api import auth, identity, maintenance
from press_tr.kimlik import oidc, request_policy, service, sessions


class RequestGuardsTest(unittest.TestCase):
	def test_identity_link_is_closed_to_generic_ai_writes(self):
		self.assertIn("Press Identity Link", getattr(hooks, "ai_write_closed_doctypes", []))
		self.assertIn("Press Keycloak Session", getattr(hooks, "ai_write_closed_doctypes", []))
		frappe.init("press.localhost")
		frappe.connect()
		try:
			for doctype in hooks.ai_write_closed_doctypes:
				self.assertTrue(frappe.db.exists("DocType", doctype))
		finally:
			frappe.destroy()

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

	def test_anonymization_suspends_only_the_sole_members_sites(self):
		from press_tr.kimlik import anonymization

		user = "old@example.test"
		with patch.object(anonymization, "frappe") as framework:
			framework.db.exists.return_value = False
			framework.db.get_value.return_value = user
			framework.get_all.side_effect = [
				["single", "shared"],
				["owned-without-members"],
				[],
				[],
				["owned-site"],
				[user, "another@example.test"],
				[],
				[user],
				[],
				["sole-site"],
			]
			owned_site, sole_site = Mock(), Mock()
			framework.get_doc.side_effect = [owned_site, sole_site]
			anonymization.clean_press_ownership(user)
			for site in (owned_site, sole_site):
				site.suspend.assert_called_once_with(reason="Account anonymized")
				site.save.assert_called_once_with(ignore_permissions=True)
				site.delete.assert_not_called()

	def test_anonymization_lock_contention_returns_conflict(self):
		from werkzeug.exceptions import Conflict

		for error in (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
			with (
				patch.object(identity, "require_service"),
				patch.object(identity, "reset_read_snapshot"),
				patch.object(identity, "anonymize_linked_user", side_effect=error),
				self.assertRaises(Conflict),
			):
				identity.anonymize_user("issuer", "subject")

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

	def test_callback_redacts_fields_before_rate_limiting(self):
		import frappe.rate_limiter

		class Rejected(Exception):
			pass

		form = {"state": "state-fixture", "code": "code-fixture"}
		with (
			patch.object(frappe.rate_limiter, "frappe") as framework,
			patch.object(auth, "frappe", framework),
		):
			framework.form_dict = frappe._dict(form)
			framework.local.request_ip = "198.18.0.1"
			framework.cache.get.return_value = 10
			framework.cache.incrby.return_value = 11

			def reject(*args):
				self.assertTrue(form.keys().isdisjoint(framework.form_dict))
				raise Rejected

			framework.throw.side_effect = reject
			with self.assertRaises(Rejected):
				auth.keycloak_callback(**form)

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

	def test_maintenance_reads_session_names_in_bounded_pages(self):
		with (
			patch.object(maintenance, "frappe") as facade,
			patch.object(maintenance, "get_expired_threshold", return_value="2026-11-22 00:00:00"),
		):
			facade.get_all.side_effect = [[f"link-{i:03}" for i in range(100)], ["link-100"]]
			facade.db.get_value.return_value = "2026-11-22 01:00:00"
			self.assertEqual(maintenance.cleanup_expired_sessions(), {"removed": 0})
			self.assertEqual(facade.get_all.call_count, 2)
			first, second = facade.get_all.call_args_list
			self.assertEqual(first.kwargs["limit"], 100)
			self.assertEqual(first.kwargs["order_by"], "name asc")
			self.assertEqual(second.kwargs["filters"], {"name": [">", "link-099"]})

	def test_frappe_1656_does_not_rewrite_the_rate_limit_command(self):
		form = {"cmd": "original"}
		with (
			patch.object(api, "frappe", SimpleNamespace(__version__="16.56.0", form_dict=form)),
			patch.object(api, "_count_rejected_logout") as count,
		):
			count.side_effect = lambda: self.assertEqual(form, {"cmd": "original"})
			api.count_rejected_logout()
			count.assert_called_once()

	def test_unknown_rpc_app_is_not_resolved(self):

		with (
			patch.object(request_policy, "frappe") as facade,
			patch.object(request_policy, "get_server_script_map", return_value={}),
			patch.object(request_policy, "get_attr", side_effect=frappe.ValidationError),
		):
			facade.override_whitelisted_method.return_value = "fixture.method"
			facade.DoesNotExistError = frappe.DoesNotExistError
			facade.PermissionError = frappe.PermissionError
			facade.ValidationError = frappe.ValidationError
			self.assertIsNone(request_policy.resolve_method("fixture.method"))
