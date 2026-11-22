"""Verify bootstrap caching respects the active session and permission generation."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.kabuk.bootstrap import SidebarContext, get_bootstrap
from platform_core.kabuk.cache import bump_permission_version


class TestBootstrapCache(IntegrationTestCase):
	def test_native_navigation_runs_once_per_generation_and_language(self):
		bump_permission_version()
		user = frappe.session.user
		with (
			patch.object(frappe.local, "lang", "en"),
			patch.object(SidebarContext, "for_modules", wraps=SidebarContext.for_modules) as build,
		):
			first = get_bootstrap(user)
			self.assertEqual(get_bootstrap(user), first)
			build.assert_called_once()

			frappe.local.lang = "tr"
			self.assertEqual(get_bootstrap(user)["user"]["language"], "tr")
			self.assertEqual(build.call_count, 2)
			frappe.local.lang = "en"
			self.assertEqual(get_bootstrap(user), first)
			self.assertEqual(build.call_count, 2)

			version = bump_permission_version()
			self.assertEqual(get_bootstrap(user)["perm_version"], version)
			self.assertEqual(build.call_count, 3)
