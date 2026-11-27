"""Risk level of a proposal: the server sets it, the model cannot (AJA-1001)."""

from unittest.mock import patch

import frappe

from platform_core.ai.tests.base import DOCTYPE, USER_A, AiTestCase

HOOK = "platform_core.ai.tests.sample_tools_risk.declare"
LEVELS = ("R0", "R1", "R2", "R3")


def with_risk_tools():
	"""Puts only the sample tools of this test in the `ai_tools` hook."""
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		if hook == "ai_tools":
			return [HOOK]
		return original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


class TestRiskLevel(AiTestCase):
	def proposal_count(self) -> int:
		return frappe.db.count("PLT AI Action Proposal")

	def stored_level(self, proposal_id: str) -> str:
		return frappe.db.get_value("PLT AI Action Proposal", proposal_id, "risk_level")

	def opened(self, result: dict) -> dict:
		self.assertFalse(result["isError"], result)
		return result["structuredContent"]

	def test_builtin_write_tools_get_the_level_of_the_rule_table(self):
		from platform_core.ai import registry, risk

		levels = {tool.name: risk.level(tool) for tool in registry.builtin_tools() if tool.kind == "write"}

		self.assertEqual(
			levels,
			{
				"plt_create_document": "R1",
				"plt_update_document": "R2",
				"plt_submit_document": "R2",
				"plt_cancel_document": "R2",
				"plt_delete_document": "R2",
				"plt_add_custom_field": "R2",
				"plt_set_field_property": "R3",
				"plt_set_role_permission": "R3",
				"plt_assign_role": "R3",
				"plt_remove_role": "R3",
				"plt_purge_action_log": "R3",
			},
		)
		for tool in registry.builtin_tools():
			if tool.kind != "write":
				self.assertEqual(risk.level(tool), "R0", tool.name)

	def test_every_new_proposal_carries_the_level_on_every_response(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)

		opened = self.propose_update(client, name, title="Yeni")
		proposal_id = opened["proposal_id"]
		human = self.human(client, "GET", "get_proposal", query={"proposal_id": proposal_id})
		listed = self.human(client, "GET", "list_proposals")
		model = self.opened(self.call_tool(client, "plt_get_proposal", {"proposal_id": proposal_id}))

		self.assertEqual(opened["risk_level"], "R2")
		self.assertEqual(self.stored_level(proposal_id), "R2")
		self.assertEqual(human.json["message"]["risk_level"], "R2")
		row = next(row for row in listed.json["message"]["proposals"] if row["proposal_id"] == proposal_id)
		self.assertEqual(row["risk_level"], "R2")
		self.assertEqual(model["risk_level"], "R2")

	def test_create_proposal_is_r1(self):
		client = self.login(USER_A)

		opened = self.opened(
			self.call_tool(client, "plt_create_document", {"doctype": DOCTYPE, "data": {"title": "Yeni"}})
		)

		self.assertIn(opened["risk_level"], LEVELS)
		self.assertEqual(self.stored_level(opened["proposal_id"]), "R1")

	def test_model_cannot_send_a_lower_level_for_a_delete(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		before = self.proposal_count()

		sent = self.call_tool(
			client, "plt_delete_document", {"doctype": DOCTYPE, "name": name, "risk_level": "R0"}
		)

		# The value is refused with the rest of the call. No proposal is opened with it.
		self.assert_denied(sent, "invalid_arguments")
		self.assertEqual(self.proposal_count(), before)
		opened = self.opened(
			self.call_tool(client, "plt_delete_document", {"doctype": DOCTYPE, "name": name})
		)
		self.assertEqual(self.stored_level(opened["proposal_id"]), "R2")

	def test_model_sent_level_does_not_change_a_stored_proposal(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]

		sent = self.call_tool(client, "plt_get_proposal", {"proposal_id": proposal_id, "risk_level": "R0"})

		self.assert_denied(sent, "invalid_arguments")
		self.assertEqual(self.stored_level(proposal_id), "R2")

	def test_app_tool_gets_the_higher_of_declared_and_computed_level(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)

		with with_risk_tools():
			low = self.opened(self.call_tool(client, "plt_low_declared_delete", {"name": name, "title": "A"}))
			high = self.opened(self.call_tool(client, "plt_high_declared_note", {"name": name, "title": "B"}))
			plain = self.opened(self.call_tool(client, "plt_plain_note", {"name": name, "title": "C"}))

		self.assertEqual(self.stored_level(low["proposal_id"]), "R2")
		self.assertEqual(self.stored_level(high["proposal_id"]), "R3")
		self.assertEqual(self.stored_level(plain["proposal_id"]), "R1")

	def test_invalid_level_declaration_and_level_argument_are_not_loaded(self):
		client = self.login(USER_A)

		with with_risk_tools():
			names = {tool["name"] for tool in self.rpc(client, "tools/list").json["result"]["tools"]}

		self.assertIn("plt_plain_note", names)
		self.assertNotIn("plt_unknown_level", names)
		self.assertNotIn("plt_level_in_arguments", names)

	def test_level_does_not_change_after_approval(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		response = self.approve(client, proposal_id)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertTrue(response.json["message"]["executed"], response.json)

		doc = frappe.get_doc("PLT AI Action Proposal", proposal_id)
		doc.risk_level = "R0"

		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)
		frappe.db.rollback()
		self.assertEqual(self.stored_level(proposal_id), "R2")

	def test_level_does_not_change_on_a_pending_proposal(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]

		doc = frappe.get_doc("PLT AI Action Proposal", proposal_id)
		doc.risk_level = "R0"

		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)

	def test_contract_defines_the_level_on_proposal_responses(self):
		import yaml

		from platform_core.ai.tests.test_registry import TestContract

		path = TestContract.CONTRACT
		if not path.exists():
			self.skipTest(f"Contract file is missing in this environment: {path}")
		contract = yaml.safe_load(path.read_text())

		for schema in (
			contract["components"]["schemas"]["Proposal"],
			contract["x-mcp-results"]["ProposalState"],
			contract["x-mcp-results"]["ApprovalRequired"],
			contract["components"]["schemas"]["ApprovalRequired"],
		):
			level = schema["properties"]["risk_level"]
			if "$ref" in level:
				level = contract["components"]["schemas"][level["$ref"].rsplit("/", 1)[-1]]
			self.assertIn("risk_level", schema["required"])
			self.assertEqual(tuple(level["enum"]), LEVELS)

	def test_migration_gives_old_proposals_the_computed_level(self):
		from platform_core.ai.patches import set_proposal_risk_level

		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		frappe.db.set_value("PLT AI Action Proposal", proposal_id, "risk_level", None, update_modified=False)

		set_proposal_risk_level.execute()

		self.assertEqual(self.stored_level(proposal_id), "R2")
