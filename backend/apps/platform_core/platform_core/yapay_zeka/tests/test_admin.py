"""Yönetim araçları: yalnız yönetici rolü, önizleme ve insan onayı."""

import frappe
from frappe.permissions import reset_perms
from frappe.utils import add_days, now_datetime

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, RESTRICTED_ROLE, USER_A, USER_B, YzTestCase

ADMIN_TOOLS = {
	"add_custom_field",
	"set_field_property",
	"set_role_permission",
	"assign_role",
	"remove_role",
	"purge_action_log",
}
EXTRA_ROLE = "YZ Ek Rol"


class TestAdminTools(YzTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Role", EXTRA_ROLE):
			frappe.get_doc(doctype="Role", role_name=EXTRA_ROLE, desk_access=0).insert()
			frappe.db.commit()  # nosemgrep

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in frappe.get_all("Custom Field", filters={"dt": DOCTYPE}, pluck="name"):
			frappe.delete_doc("Custom Field", name, force=True)
		for name in frappe.get_all("Property Setter", filters={"doc_type": DOCTYPE}, pluck="name"):
			frappe.delete_doc("Property Setter", name, force=True)
		reset_perms(DOCTYPE)
		user = frappe.get_doc("User", USER_B)
		user.remove_roles(EXTRA_ROLE)
		frappe.clear_cache(doctype=DOCTYPE)
		frappe.db.commit()  # nosemgrep
		super().tearDown()

	def tools(self, client) -> set[str]:
		return {tool["name"] for tool in self.rpc(client, "tools/list").json["result"]["tools"]}

	def propose(self, client, tool: str, arguments: dict, **kwargs) -> dict:
		result = self.call_tool(client, tool, arguments, **kwargs)
		self.assertFalse(result["isError"], result)
		self.assertEqual(result["structuredContent"]["status"], "approval_required")
		return result["structuredContent"]

	def test_admin_tools_are_hidden_from_and_denied_to_other_users(self):
		client = self.login(USER_A)
		manager = self.login(MANAGER)

		denied = self.call_tool(
			client,
			"add_custom_field",
			{
				"doctype": DOCTYPE,
				"fieldname": "yz_ek",
				"label": "Ek",
				"fieldtype": "Data",
				"description": "Extra.",
			},
		)

		self.assertFalse(self.tools(client) & ADMIN_TOOLS)
		self.assertLessEqual(ADMIN_TOOLS, self.tools(manager))
		self.assert_denied(denied, "role_required")
		log = self.last_log(tool="add_custom_field", user=USER_A)
		self.assertEqual((log.decision, log.tool_class), ("denied", "admin"))

	def test_admin_functions_check_the_role_themselves(self):
		"""Araç listesi atlanırsa bile işlevler yönetici rolünü denetler."""
		from platform_core.yapay_zeka import retention
		from platform_core.yapay_zeka.tools import admin

		frappe.set_user(USER_A)
		calls = (
			lambda: admin.preview_custom_field(
				DOCTYPE, "yz_x", label="X", fieldtype="Data", description="X."
			),
			lambda: admin.run_field_property(DOCTYPE, "title", "reqd", True),
			lambda: admin.run_role_permission(DOCTYPE, RESTRICTED_ROLE, {"delete": False}),
			lambda: admin.run_assign_role(USER_B, EXTRA_ROLE),
			lambda: retention.purge(365, dry_run=False),
		)

		for call in calls:
			self.assertRaises(frappe.PermissionError, call)

	def test_custom_field_is_added_only_after_approval(self):
		manager = self.login(MANAGER)
		arguments = {
			"doctype": DOCTYPE,
			"fieldname": "yz_renk",
			"label": "Renk",
			"fieldtype": "Select",
			"options": "Kirmizi\nMavi",
			"description": "Colour of the record.",
		}

		proposal = self.propose(manager, "add_custom_field", arguments)
		before = frappe.get_meta(DOCTYPE).has_field("yz_renk")
		outcome = self.approve(manager, proposal["proposal_id"]).json["message"]
		frappe.clear_cache(doctype=DOCTYPE)
		field = frappe.get_meta(DOCTYPE).get_field("yz_renk")

		self.assertFalse(before)
		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual((field.fieldtype, field.description), ("Select", "Colour of the record."))

	def test_custom_field_needs_a_description_and_rejects_expressions(self):
		manager = self.login(MANAGER)
		base = {"doctype": DOCTYPE, "fieldname": "yz_x", "label": "X", "fieldtype": "Data"}

		no_description = self.call_tool(manager, "add_custom_field", base)
		expression = self.call_tool(
			manager, "add_custom_field", {**base, "description": "X.", "depends_on": "eval:1"}
		)
		existing = self.call_tool(
			manager, "add_custom_field", {**base, "fieldname": "title", "description": "Duplicate."}
		)
		closed = self.call_tool(
			manager, "add_custom_field", {**base, "doctype": "AI Action Log", "description": "X."}
		)

		self.assert_denied(no_description, "invalid_arguments")
		self.assert_denied(expression, "invalid_arguments")
		self.assert_denied(existing, "invalid_arguments")
		self.assert_denied(closed, "blocked_doctype")

	def test_field_property_changes_only_after_approval(self):
		manager = self.login(MANAGER)

		proposal = self.propose(
			manager,
			"set_field_property",
			{"doctype": DOCTYPE, "fieldname": "title", "property": "reqd", "value": True},
		)
		before = frappe.get_meta(DOCTYPE).get_field("title").reqd
		outcome = self.approve(manager, proposal["proposal_id"]).json["message"]
		frappe.clear_cache(doctype=DOCTYPE)
		forbidden = self.call_tool(
			manager,
			"set_field_property",
			{"doctype": DOCTYPE, "fieldname": "title", "property": "depends_on", "value": "eval:1"},
		)

		self.assertEqual(proposal["preview"]["changes"][0]["old"], 0)
		self.assertFalse(before)
		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("title").reqd, 1)
		self.assert_denied(forbidden, "invalid_arguments")

	def test_role_permission_changes_only_after_approval(self):
		manager = self.login(MANAGER)
		client = self.login(USER_A)
		name = self.make_record(USER_A)
		target = {"doctype": DOCTYPE, "name": name}
		arguments = {"doctype": DOCTYPE, "role": RESTRICTED_ROLE, "permissions": {"delete": False}}

		proposal = self.propose(manager, "set_role_permission", arguments)
		before = self.call_tool(client, "delete_document", target)
		outcome = self.approve(manager, proposal["proposal_id"]).json["message"]
		after = self.call_tool(client, "delete_document", target)
		still_reads = self.call_tool(client, "get_document", target)

		self.assertFalse(before["isError"], before)
		self.assertTrue(outcome["executed"], outcome)
		self.assert_denied(after, "permission")
		self.assertFalse(still_reads["isError"], still_reads)

	def test_role_permission_rejects_guest_role_and_unknown_types(self):
		manager = self.login(MANAGER)

		guest = self.call_tool(
			manager,
			"set_role_permission",
			{"doctype": DOCTYPE, "role": "Guest", "permissions": {"read": True}},
		)
		unknown = self.call_tool(
			manager,
			"set_role_permission",
			{"doctype": DOCTYPE, "role": RESTRICTED_ROLE, "permissions": {"ignore": True}},
		)

		self.assert_denied(guest, "protected_role")
		self.assert_denied(unknown, "invalid_arguments")

	def test_permission_change_made_after_preview_invalidates_the_approval(self):
		manager = self.login(MANAGER)
		proposal = self.propose(
			manager,
			"set_role_permission",
			{"doctype": DOCTYPE, "role": RESTRICTED_ROLE, "permissions": {"delete": False}},
		)
		digest = self.digest_of(manager, proposal["proposal_id"])
		from frappe.permissions import update_permission_property

		update_permission_property(DOCTYPE, RESTRICTED_ROLE, 0, "cancel", 0)
		frappe.clear_cache(doctype=DOCTYPE)

		outcome = self.approve(manager, proposal["proposal_id"], digest).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["deny_reason"], "document_changed")

	def test_role_is_assigned_and_removed_only_after_approval(self):
		manager = self.login(MANAGER)

		give = self.propose(manager, "assign_role", {"user": USER_B, "role": EXTRA_ROLE})
		before = EXTRA_ROLE in frappe.get_roles(USER_B)
		self.assertTrue(self.approve(manager, give["proposal_id"]).json["message"]["executed"])
		frappe.clear_cache(user=USER_B)
		given = EXTRA_ROLE in frappe.get_roles(USER_B)
		take = self.propose(manager, "remove_role", {"user": USER_B, "role": EXTRA_ROLE})
		self.assertTrue(self.approve(manager, take["proposal_id"]).json["message"]["executed"])
		frappe.clear_cache(user=USER_B)

		self.assertFalse(before)
		self.assertTrue(given)
		self.assertNotIn(EXTRA_ROLE, frappe.get_roles(USER_B))

	def test_protected_roles_cannot_be_assigned(self):
		manager = self.login(MANAGER)

		result = self.call_tool(manager, "assign_role", {"user": USER_B, "role": "System Manager"})

		self.assert_denied(result, "protected_role")

	def test_agent_token_of_a_manager_can_only_propose(self):
		manager = self.login(MANAGER)
		token = self.issue_token(manager)

		proposal = self.propose(
			self.anonymous(), "assign_role", {"user": USER_B, "role": EXTRA_ROLE}, token=token
		)

		self.assertNotIn(EXTRA_ROLE, frappe.get_roles(USER_B))
		self.assertEqual(
			frappe.db.get_value("AI Action Proposal", proposal["proposal_id"], "principal"), "agent_token"
		)

	def old_log(self, days: int) -> str:
		name = (
			frappe.get_doc(
				doctype="AI Action Log",
				user=MANAGER,
				principal="human_session",
				stage="call",
				decision="allowed",
			)
			.insert()
			.name
		)
		frappe.db.set_value(
			"AI Action Log", name, "creation", add_days(now_datetime(), -days), update_modified=False
		)
		frappe.db.commit()  # nosemgrep
		return name

	def test_purge_tool_deletes_only_old_logs_after_approval(self):
		manager = self.login(MANAGER)
		old, recent = self.old_log(400), self.old_log(10)

		too_short = self.call_tool(manager, "purge_action_log", {"older_than_days": 30})
		proposal = self.propose(manager, "purge_action_log", {})
		untouched = frappe.db.exists("AI Action Log", old)
		outcome = self.approve(manager, proposal["proposal_id"]).json["message"]

		self.assert_denied(too_short, "invalid_arguments")
		self.assertGreaterEqual(proposal["preview"]["details"]["logs"], 1)
		self.assertTrue(untouched)
		self.assertTrue(outcome["executed"], outcome)
		self.assertFalse(frappe.db.exists("AI Action Log", old))
		self.assertTrue(frappe.db.exists("AI Action Log", recent))

	def test_purge_endpoint_is_dry_by_default_and_admin_only(self):
		manager = self.login(MANAGER)
		client = self.login(USER_A)
		old = self.old_log(400)

		forbidden = self.human(client, "POST", "purge_logs", body={})
		dry = self.human(manager, "POST", "purge_logs", body={}).json["message"]
		still_there = frappe.db.exists("AI Action Log", old)
		short = self.human(manager, "POST", "purge_logs", body={"older_than_days": 10, "dry_run": False})
		real = self.human(manager, "POST", "purge_logs", body={"dry_run": False}).json["message"]

		self.assertEqual(forbidden.status_code, 403)
		self.assertTrue(dry["dry_run"])
		self.assertGreaterEqual(dry["logs"], 1)
		self.assertTrue(still_there)
		self.assertEqual(short.status_code, 417)
		self.assertFalse(real["dry_run"])
		self.assertFalse(frappe.db.exists("AI Action Log", old))

	def test_purge_keeps_proposals_with_unknown_result(self):
		manager = self.login(MANAGER)
		name = self.make_record(MANAGER)
		done = self.propose(
			manager, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "1"}}
		)
		self.human(manager, "POST", "reject_proposal", body={"proposal_id": done["proposal_id"]})
		other = self.make_record(MANAGER)
		stuck = self.propose(
			manager, "update_document", {"doctype": DOCTYPE, "name": other, "data": {"title": "2"}}
		)
		frappe.db.set_value(
			"AI Action Proposal", stuck["proposal_id"], {"status": "consumed", "result": "unknown"}
		)
		for proposal in (done, stuck):
			frappe.db.set_value(
				"AI Action Proposal",
				proposal["proposal_id"],
				"creation",
				add_days(now_datetime(), -400),
				update_modified=False,
			)

		self.human(manager, "POST", "purge_logs", body={"dry_run": False})

		self.assertFalse(frappe.db.exists("AI Action Proposal", done["proposal_id"]))
		self.assertTrue(frappe.db.exists("AI Action Proposal", stuck["proposal_id"]))
