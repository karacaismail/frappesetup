"""Check the logout token size before signature verification."""

from unittest import TestCase
from unittest.mock import patch

import frappe
from werkzeug.exceptions import ServiceUnavailable

from press_tr import api


class LogoutTokenSizeTest(TestCase):
	def test_oversized_token_is_rejected_before_signature_verification(self):
		with (
			patch.object(api, "client_id", return_value="press"),
			patch.object(api, "reject", side_effect=frappe.PermissionError),
			patch.object(api, "count_rejected_logout") as count_rejection,
			patch.object(api, "verify", side_effect=frappe.PermissionError) as verify,
		):
			with self.assertRaises(frappe.PermissionError):
				api._revoke_keycloak_sessions("a" * 8193)
			verify.assert_not_called()
			count_rejection.assert_called_once_with()

	def test_storage_failure_hides_decrypted_session_values(self):
		with (
			patch.object(api, "client_id", return_value="press"),
			patch.object(api, "verify", return_value={"sid": "fixture-keycloak-session"}),
			patch.object(api, "session_mapping_pages", return_value=[["fixture-mapping"]]),
			patch.object(api, "read_press_session_id", return_value="fixture-private-session"),
			patch.object(api, "frappe") as framework,
		):
			framework.qb.from_.side_effect = RuntimeError("fixture-private-session")
			with self.assertRaises(ServiceUnavailable) as raised:
				api._revoke_keycloak_sessions("fixture-token")
		self.assertTrue(raised.exception.__suppress_context__)
		self.assertNotIn("fixture-private-session", str(raised.exception))
