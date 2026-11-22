"""Verify the native authentication gates behind Press machine routes."""

import json
import subprocess
import unittest
from inspect import unwrap
from pathlib import Path
from unittest.mock import Mock, patch

import frappe
import press
import stripe
import yaml
from press.api import email, monitoring, site_backup
from press.press.doctype.github_webhook_log import github_webhook_log as github_log
from press.press.doctype.stripe_webhook_log import stripe_webhook_log as stripe_log
from test_auth_http import PressHttpClient

from press_tr import api
from press_tr.api import auth
from press_tr.kimlik import request_policy
from press_tr.kimlik.machine_routes import machine_targets

CONTRACT = Path(__file__).with_name("press_tr.openapi.yaml")


class MachineRoutesTest(PressHttpClient, unittest.TestCase):
	def setUp(self):
		super().setUp()
		frappe.init("press.localhost")
		frappe.connect()
		self.addCleanup(frappe.destroy)

	def test_pinned_press_auth_contract(self):
		from press import hooks

		repo = Path(press.__file__).resolve().parents[1]
		tag = subprocess.check_output(
			["git", "-C", str(repo), "describe", "--tags", "--exact-match"], text=True
		).strip()
		self.assertEqual(tag, "v0.154.1")
		self.assertIn("press.auth.hook", hooks.auth_hooks)

	def test_registered_guest_functions_are_denied_outside_the_contract(self):
		contract = yaml.safe_load(CONTRACT.read_text())["x-press-machine-routes"]
		expected_machine_routes = {path.removeprefix("/api/method/") for path in contract}
		machines = machine_targets()
		self.assertEqual(set(machines.values()), expected_machine_routes)
		allowed = {frappe.ping, auth.get_login_url, auth.keycloak_callback, api.keycloak_backchannel_logout}
		by_name = {
			"press_tr.api.auth.get_login_url": auth.get_login_url,
			"press_tr.api.auth.keycloak_callback": auth.keycloak_callback,
			"press_tr.api.keycloak_backchannel_logout": api.keycloak_backchannel_logout,
		}
		guest_functions = tuple(frappe.guest_methods)
		self.assertTrue(guest_functions)
		with patch.object(request_policy, "frappe") as facade:
			facade.session.user = "Guest"
			facade.ping = frappe.ping
			facade.get_attr.side_effect = by_name.__getitem__
			facade.PermissionError = frappe.PermissionError
			facade.throw.side_effect = frappe.PermissionError
			for target in guest_functions:
				with self.subTest(target=target):
					facade.local.press_request_target = (target, {})
					if target in allowed or target in machines:
						request_policy.enforce_guest_allowlist()
					else:
						with self.assertRaises(frappe.PermissionError):
							request_policy.enforce_guest_allowlist()

	def test_native_login_aliases_resolve_to_blocked_functions(self):
		from press.api import account, oauth, saas
		from press.api.developer import saas as developer_saas

		targets = request_policy.blocked_identity_targets()
		self.assertIn(account.update_password, targets)
		self.assertIn(oauth.setup_account, targets)
		self.assertIn(saas.headless_setup_account, targets)
		self.assertIn(developer_saas.login_to_fc, targets)

	def test_each_saas_machine_route_requires_site_credentials(self):
		routes = yaml.safe_load(CONTRACT.read_text())["x-press-machine-routes"]
		tested = []
		for path, settings in routes.items():
			if settings["credential"] == "saas":
				with self.subTest(path=path):
					self.assertEqual(self.request("POST", path)[0], 401)
				tested.append(path)
		self.assertTrue(tested)

	def test_saas_token_validation_returns_false_for_unknown_credentials(self):
		status, _, payload = self.exchange(
			"POST",
			"/api/method/press.saas.api.auth.is_access_token_valid",
			{"Content-Type": "application/json"},
			json.dumps({"token": "unknown-test-token:invalid"}),
		)
		self.assertEqual(status, 200)
		self.assertIs(json.loads(payload)["message"], False)

	def test_stripe_rejects_invalid_signature(self):
		with (
			patch.object(stripe_log, "frappe") as facade,
			patch.object(stripe_log, "get_stripe", return_value=stripe),
		):
			facade.db.get_single_value.return_value = "whsec_fixture"
			facade.throw.side_effect = stripe_log.InvalidStripeWebhookEvent
			with self.assertRaises(stripe_log.InvalidStripeWebhookEvent):
				stripe_log.parse_payload(b"{}", "t=0,v1=invalid")

	def test_github_rejects_invalid_signature_before_parsing_events(self):
		doc = Mock(payload="{}", signature="invalid")
		with patch.object(github_log, "frappe") as facade:
			facade.db.get_single_value.return_value = "fixture"
			facade.throw.side_effect = frappe.ValidationError
			with self.assertRaises(frappe.ValidationError):
				github_log.GitHubWebhookLog.validate(doc)
			doc.get_parsed_payload.assert_not_called()

	def test_monitoring_rejects_invalid_tokens_before_reading_or_writing(self):
		with (
			patch.object(monitoring, "frappe") as facade,
			patch.object(monitoring, "get_benches") as get_benches,
			patch.object(monitoring, "log_error"),
		):
			facade.db.get_single_value.return_value = "fixture"
			self.assertIsNone(unwrap(monitoring.targets)("invalid"))
			get_benches.assert_not_called()

			facade.request.args = {"webhook_token": "invalid"}
			facade.db.get_value.return_value = "fixture"
			facade.AuthenticationError = frappe.AuthenticationError
			facade.session.user = "Guest"
			monitoring.alert()
			facade.get_doc.assert_not_called()

	def test_email_rejects_unknown_subscription_before_sending(self):
		with (
			patch.object(email, "frappe") as facade,
			patch.object(email, "get_subscription_info", side_effect=frappe.DoesNotExistError),
			patch.object(email.requests, "post") as send,
		):
			facade._dict.return_value = {}
			facade.throw.side_effect = frappe.DoesNotExistError
			with self.assertRaises(frappe.DoesNotExistError):
				unwrap(email.send_mime_mail)(json.dumps({"sk_mail": "unknown"}))
			send.assert_not_called()

	def test_backup_rejects_wrong_snapshot_key(self):
		with patch.object(site_backup, "frappe") as facade:
			backup = Mock(snapshot_request_key="fixture")
			facade.get_doc.return_value = backup
			facade.throw.side_effect = frappe.ValidationError
			with self.assertRaises(frappe.ValidationError):
				unwrap(site_backup.create_snapshot)("fixture", "invalid")
			backup.create_database_snapshot.assert_not_called()

	def test_account_request_cannot_create_native_invitation(self):
		from press.press.doctype.account_request.account_request import AccountRequest

		doc = frappe.get_doc({"doctype": "Account Request", "invited_by": "fixture@example.test"})
		with patch.object(AccountRequest, "before_insert") as native:
			with self.assertRaises(frappe.PermissionError):
				doc.run_method("before_insert")
			native.assert_not_called()
