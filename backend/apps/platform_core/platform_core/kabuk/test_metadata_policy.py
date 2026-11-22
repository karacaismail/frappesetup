"""Check the shell's use of the trusted mobile identity."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.wrappers import Request

from platform_core.api.meta import validate_mobile_policy
from platform_core.kabuk.metadata_policy import verified_mobile_request


class TestMobileIdentityContract(IntegrationTestCase):
	def test_policy_check_rejects_unknown_query_parameters(self):
		with (
			patch.object(frappe.local, "response_headers", {}, create=True),
			patch.object(frappe.local, "form_dict", frappe._dict(unexpected="test"), create=True),
			self.assertRaises(frappe.ValidationError),
		):
			validate_mobile_policy()

	def test_policy_diagnostics_follow_the_request_language(self):
		with (
			patch.object(frappe.local, "lang", "tr", create=True),
			patch.object(frappe.local, "response_headers", {}, create=True),
			patch.object(frappe.local, "form_dict", frappe._dict(), create=True),
			patch.dict(frappe.conf, {"shell_mobile_doctypes": "invalid"}),
		):
			result = validate_mobile_policy()

		self.assertFalse(result["valid"])
		self.assertEqual(
			result["errors"],
			[
				"shell_mobile_doctypes ayar\u0131 kay\u0131t türü adlar\u0131ndan oluşan bir liste olmal\u0131d\u0131r."
			],
		)

	def test_installation_requires_the_contract_format(self):
		request = Request.from_values(path="/api/method/platform_core.api.mobile.get_metadata")
		identity = {
			"account": frappe.session.user,
			"scope": "mobile",
			"site": frappe.local.site,
			"sid": "test-session",
		}
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "mobile_identity", identity, create=True),
		):
			for installation in ("a", "A0_-", "a" * 128):
				with self.subTest(installation=installation):
					identity["installation"] = installation
					self.assertTrue(verified_mobile_request(frappe.session.user))
			for installation in ("", "a" * 129, "a b", "a/b", "a\n", "\u0130", None):
				with self.subTest(installation=installation):
					identity["installation"] = installation
					self.assertFalse(verified_mobile_request(frappe.session.user))

	def test_raw_header_does_not_supply_a_trusted_installation(self):
		request = Request.from_values(
			path="/api/method/platform_core.api.mobile.get_metadata",
			headers={"X-Platform-Installation": "unverified"},
		)
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "mobile_identity", None, create=True),
		):
			self.assertFalse(verified_mobile_request(frappe.session.user))
