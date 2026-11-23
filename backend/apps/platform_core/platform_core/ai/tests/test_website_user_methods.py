"""Methods of the AI access layer that a Website User may call (contract: section on the allow list).

An end user works in the panel as a Website User. They talk to the layer and decide on their own
proposals, so those methods are on the `website_user_allowed_methods` hook. Deleting old records
needs the System Manager role, so that method is not on the list.
"""

import frappe

from platform_core.ai.tests.base import AiTestCase

OPEN = {
	"platform_core.api.ai.mcp",
	"platform_core.api.ai.mcp_resource_metadata",
	"platform_core.api.ai.issue_agent_token",
	"platform_core.api.ai.list_proposals",
	"platform_core.api.ai.get_proposal",
	"platform_core.api.ai.approve_proposal",
	"platform_core.api.ai.reject_proposal",
	"platform_core.api.ai.resolve_proposal",
}


class TestWebsiteUserMethods(AiTestCase):
	def test_the_layer_lists_its_end_user_methods_and_nothing_else(self):
		listed = {name for name in frappe.get_hooks("website_user_allowed_methods") if ".api.ai." in name}

		self.assertEqual(listed, OPEN)

	def test_every_listed_method_is_a_whitelisted_function(self):
		for name in sorted(OPEN):
			self.assertIn(frappe.get_attr(name), frappe.whitelisted, name)


class TestWebsiteUserOverHttp(AiTestCase):
	"""An end user is a Website User. Each endpoint of the list answers them over HTTP."""

	def test_a_website_user_proposes_reads_and_decides_over_http(self):
		from platform_core.ai.tests.base import DOCTYPE, USER_A

		self.assertEqual(frappe.db.get_value("User", USER_A, "user_type"), "Website User")
		first = self.make_record(USER_A, title="Old")
		second = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		token = self.human(client, "POST", "issue_agent_token")
		self.assertEqual(token.status_code, 200, token.get_data(as_text=True))
		proposal = self.propose_update(client, first, title="New")["proposal_id"]
		listed = self.human(client, "GET", "list_proposals", query={"status": "pending"})
		self.assertEqual(listed.status_code, 200)
		self.assertIn(proposal, [row["proposal_id"] for row in listed.json["message"]["proposals"]])
		approved = self.approve(client, proposal)
		self.assertEqual(approved.status_code, 200)
		self.assertTrue(approved.json["message"]["executed"], approved.json)
		self.assertEqual(frappe.db.get_value(DOCTYPE, first, "title"), "New")

		other = self.propose_update(client, second, title="New")["proposal_id"]
		rejected = self.human(client, "POST", "reject_proposal", body={"proposal_id": other})
		self.assertEqual(rejected.status_code, 200, rejected.get_data(as_text=True))
		self.assertEqual(frappe.db.get_value(DOCTYPE, second, "title"), "Old")
		# Nothing has an unknown result here. The endpoint is reached and answers with a state error.
		resolved = self.human(
			client, "POST", "resolve_proposal", body={"proposal_id": other, "outcome": "failed"}
		)
		self.assertNotIn(resolved.status_code, (401, 403), resolved.get_data(as_text=True))

	def test_a_website_user_cannot_delete_old_records(self):
		from platform_core.ai.tests.base import USER_A

		client = self.login(USER_A)

		response = self.human(client, "POST", "purge_logs", body={"older_than_days": 365, "dry_run": True})

		self.assertEqual(response.status_code, 403)
		self.assertNotIn("platform_core.api.ai.purge_logs", frappe.get_hooks("website_user_allowed_methods"))
