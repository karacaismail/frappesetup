import frappe
from frappe.tests import IntegrationTestCase

from platform_core.hooks import doc_events


class TestShellPermissionHooks(IntegrationTestCase):
	def test_permission_hook_doctypes_exist_on_the_site(self):
		for doctype, events in doc_events.items():
			if not any(str(hook).startswith("platform_core.kabuk.cache.") for hook in events.values()):
				continue
			with self.subTest(doctype=doctype):
				self.assertEqual(frappe.db.exists("DocType", doctype), doctype)
