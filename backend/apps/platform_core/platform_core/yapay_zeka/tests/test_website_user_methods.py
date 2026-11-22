"""Methods of the AI access layer that a Website User may call (contract: section on the allow list).

An end user works in the panel as a Website User. They talk to the layer and decide on their own
proposals, so those methods are on the `website_user_allowed_methods` hook. Deleting old records
needs the System Manager role, so that method is not on the list.
"""

import frappe

from platform_core.yapay_zeka.tests.base import YzTestCase

OPEN = {
	"platform_core.api.ai.mcp",
	"platform_core.api.ai.issue_agent_token",
	"platform_core.api.ai.list_proposals",
	"platform_core.api.ai.get_proposal",
	"platform_core.api.ai.approve_proposal",
	"platform_core.api.ai.reject_proposal",
	"platform_core.api.ai.resolve_proposal",
}


class TestWebsiteUserMethods(YzTestCase):
	def test_the_layer_lists_its_end_user_methods_and_nothing_else(self):
		listed = {name for name in frappe.get_hooks("website_user_allowed_methods") if ".api.ai." in name}

		self.assertEqual(listed, OPEN)

	def test_every_listed_method_is_a_whitelisted_function(self):
		for name in sorted(OPEN):
			self.assertIn(frappe.get_attr(name), frappe.whitelisted, name)
