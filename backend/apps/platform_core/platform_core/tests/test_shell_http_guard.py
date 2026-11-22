import unittest
from unittest.mock import Mock, patch

from platform_core.tests.shell_http_fixture import SITE, ShellHTTPFixture


class TestShellHTTPGuard(unittest.TestCase):
	def test_without_opt_in_does_not_touch_frappe(self):
		with (
			patch.dict("os.environ", {}, clear=True),
			patch("platform_core.tests.shell_http_fixture.frappe") as frappe,
		):
			frappe.init.side_effect = AssertionError("Unexpected Frappe initialization.")
			with self.assertRaises(unittest.SkipTest):
				ShellHTTPFixture.setUpClass()
			frappe.init.assert_not_called()
			frappe.connect.assert_not_called()
			frappe.destroy.assert_not_called()

	def test_connection_must_bind_the_isolated_site_before_fixtures(self):
		with (
			patch.dict("os.environ", {"KABUK_TEST_SITE": SITE}),
			patch("platform_core.tests.shell_http_fixture.frappe") as frappe,
		):
			frappe.local.site = None
			frappe.init.side_effect = lambda **kwargs: setattr(frappe.local, "site", SITE)
			frappe.connect.side_effect = lambda: setattr(frappe.local, "site", "another-test.localhost")
			frappe.conf.allow_tests = True
			frappe.set_user.side_effect = AssertionError("Unexpected fixture setup.")
			with patch.object(ShellHTTPFixture, "addClassCleanup", Mock()):
				with self.assertRaisesRegex(RuntimeError, "isolated site"):
					ShellHTTPFixture.setUpClass()
			frappe.set_user.assert_not_called()
			frappe.db.exists.assert_not_called()
