"""The /panel page context: bundle assets, CSP nonce, CSRF meta and the guest redirect (E-3)."""

import json
import os
import secrets
import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.shell.panel_assets import ENV_KEY, SITE_CONFIG_KEY
from platform_core.www import panel

MANIFEST = {
	"index.html": {
		"file": "assets/index-1.js",
		"isEntry": True,
		"imports": ["_vendor-2.js"],
		"css": ["assets/index-3.css"],
	},
	"_vendor-2.js": {"file": "assets/vendor-2.js"},
}
PLACEHOLDER_POLICY = (
	"default-src 'self'; script-src 'self'; frame-ancestors 'none'; "
	"object-src 'none'; base-uri 'self'; form-action 'self'"
)


def app_policy(nonce):
	return (
		f"default-src 'self'; script-src 'self'; style-src 'self' 'nonce-{nonce}'; "
		"frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
	)


class TestPanelPage(IntegrationTestCase):
	def setUp(self):
		# A fresh value per test: a fixed default here looks like a hard coded password (Bandit B107).
		self.token = secrets.token_hex(16)
		self.folder = tempfile.TemporaryDirectory()
		self.addCleanup(self.folder.cleanup)
		self.manifest = Path(self.folder.name) / ".vite" / "manifest.json"
		self.manifest.parent.mkdir()
		self.manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
		frappe.local.response_headers = {}
		self.addCleanup(setattr, frappe.local, "response_headers", {})
		self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)
		self.path = patch.object(frappe.local, "path", "panel", create=True)
		self.path.start()
		self.addCleanup(self.path.stop)
		environment = patch.dict(os.environ, clear=False)
		environment.start()
		self.addCleanup(environment.stop)
		os.environ.pop(ENV_KEY, None)
		self.conf = patch.dict(frappe.local.conf, {SITE_CONFIG_KEY: str(self.manifest)})
		self.conf.start()
		self.addCleanup(self.conf.stop)

	def render(self, signed_in=True):
		context = frappe._dict()
		with (
			patch.object(panel, "has_session_cookie", return_value=signed_in),
			patch.object(panel, "get_csrf_token", return_value=self.token),
		):
			panel.get_context(context)
		return context, dict(frappe.local.response_headers)

	def test_signed_in_page_loads_the_bundle_with_a_nonce(self):
		context, headers = self.render()
		self.assertEqual(context.panel_assets.script, "/panel/assets/index-1.js")
		self.assertEqual(context.panel_assets.styles, ("/panel/assets/index-3.css",))
		self.assertEqual(context.panel_assets.preloads, ("/panel/assets/vendor-2.js",))
		self.assertEqual(context.panel_csrf_token, self.token)
		self.assertGreaterEqual(len(context.panel_csp_nonce), 22)
		self.assertEqual(headers["Content-Security-Policy"], app_policy(context.panel_csp_nonce))
		self.assertEqual(headers["Cache-Control"], "private, no-store")
		self.assertEqual(headers["X-Frame-Options"], "DENY")

	def test_each_response_has_its_own_nonce(self):
		first, _unused = self.render()
		second, _unused = self.render()
		self.assertNotEqual(first.panel_csp_nonce, second.panel_csp_nonce)

	def test_environment_variable_names_the_manifest(self):
		self.conf.stop()
		with patch.dict(os.environ, {ENV_KEY: str(self.manifest)}):
			context, _unused = self.render()
		self.conf.start()
		self.assertEqual(context.panel_assets.script, "/panel/assets/index-1.js")

	def test_missing_manifest_keeps_the_placeholder(self):
		self.manifest.unlink()
		with self.assertLogs("platform_core.shell.panel_assets", level="WARNING"):
			context, headers = self.render()
		self.assertIsNone(context.panel_assets)
		self.assertIsNone(context.get("panel_csp_nonce"))
		self.assertEqual(context.panel_csrf_token, self.token)
		self.assertEqual(headers["Content-Security-Policy"], PLACEHOLDER_POLICY)

	def test_guest_is_redirected_without_token_or_assets(self):
		with self.assertRaises(frappe.Redirect):
			self.render(signed_in=False)
		self.assertEqual(frappe.local.flags.redirect_location, "/login?redirect-to=/panel")
		headers = frappe.local.response_headers
		self.assertEqual(headers["Content-Security-Policy"], PLACEHOLDER_POLICY)
		self.assertEqual(headers["Cache-Control"], "private, no-store")

	def test_guest_deep_link_returns_to_the_same_panel_route(self):
		self.path.stop()
		with patch.object(frappe.local, "path", "panel/records/Sample Record", create=True):
			with self.assertRaises(frappe.Redirect):
				self.render(signed_in=False)
		self.path.start()
		self.assertEqual(
			frappe.local.flags.redirect_location, "/login?redirect-to=/panel/records/Sample%20Record"
		)

	def test_guest_browser_navigation_returns_to_record_after_login(self):
		self.path.stop()
		with (
			patch.object(frappe.local, "path", "panel/hrms/leave-application/missing-record", create=True),
			patch.object(frappe, "get_request_header", return_value="?1"),
			self.assertRaises(frappe.Redirect),
		):
			self.render(signed_in=False)
		self.path.start()
		self.assertEqual(
			frappe.local.flags.redirect_location,
			"/login?redirect-to=%2Fpanel%2Fhrms%2Fleave-application%2Fmissing-record",
		)

	def test_client_routes_render_the_panel_page(self):
		rules = frappe.get_hooks("website_route_rules", app_name="platform_core")
		self.assertIn({"from_route": "/panel/<path:app_path>", "to_route": "panel"}, rules)
