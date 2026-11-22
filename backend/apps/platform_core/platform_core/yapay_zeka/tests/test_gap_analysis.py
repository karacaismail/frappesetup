"""Rules from the independent gap analysis.

O1: a desk role is never proposed for an end user (Website User). Frappe would turn that user into
    a System User (`frappe/core/doctype/user/user.py`, `set_system_user`).
O14: the identity link is closed to AI writes. The access rule changes only through admin tools.
O6: a commit inside a request never carries writes that are not the layer's own.
O7: the human proposal list uses one bounded query.
K5: the permission bypass of the layer's own records does not stay on the document.
K11: a report meant for background preparation is not run in the request.
The report gate is reached through the access engine's public path.
"""

import sys
from types import ModuleType
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime, set_request

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, USER_B, YzTestCase

DESK_ROLE = "AI Test Desk Role"
PORTAL_ROLE = "AI Test Portal Role"
REPORT = "Permitted Documents For User"
GATE = "platform_core.erisim.api"


def ensure_role(name: str, desk_access: int) -> None:
	if not frappe.db.exists("Role", name):
		frappe.get_doc(doctype="Role", role_name=name, desk_access=desk_access).insert()
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection


class TestDeskRoleForEndUser(YzTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_role(DESK_ROLE, 1)
		ensure_role(PORTAL_ROLE, 0)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for user in (USER_B, MANAGER):
			frappe.get_doc("User", user).remove_roles(DESK_ROLE, PORTAL_ROLE)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		super().tearDown()

	def test_desk_role_is_refused_for_a_website_user(self):
		manager = self.login(MANAGER)

		result = self.call_tool(manager, "assign_role", {"user": USER_B, "role": DESK_ROLE})

		self.assert_denied(result, "desk_role_for_end_user")
		self.assertEqual(frappe.db.get_value("User", USER_B, "user_type"), "Website User")
		log = self.last_log(tool="assign_role", deny_reason="desk_role_for_end_user")
		self.assertEqual((log.user, log.decision), (MANAGER, "denied"))

	def test_portal_role_is_proposed_for_a_website_user(self):
		manager = self.login(MANAGER)

		result = self.call_tool(manager, "assign_role", {"user": USER_B, "role": PORTAL_ROLE})

		self.assertFalse(result["isError"], result)

	def test_desk_role_is_proposed_for_a_system_user(self):
		manager = self.login(MANAGER)

		result = self.call_tool(manager, "assign_role", {"user": MANAGER, "role": DESK_ROLE})

		self.assertFalse(result["isError"], result)

	def test_execution_checks_the_desk_rule_again(self):
		from platform_core.yapay_zeka.errors import ToolDenied
		from platform_core.yapay_zeka.tools import admin

		frappe.set_user(MANAGER)

		with self.assertRaises(ToolDenied) as raised:
			admin.prepare_assign_role(USER_B, DESK_ROLE)

		self.assertEqual(raised.exception.code, "desk_role_for_end_user")


class TestClosedDoctypes(YzTestCase):
	def test_identity_link_is_closed_to_every_ai_write(self):
		manager = self.login(MANAGER)
		link = "Platform Identity Link"

		created = self.call_tool(manager, "create_document", {"doctype": link, "data": {"issuer": "x"}})
		updated = self.call_tool(
			manager, "update_document", {"doctype": link, "name": "x", "data": {"user": "y"}}
		)
		deleted = self.call_tool(manager, "delete_document", {"doctype": link, "name": "x"})
		field = self.call_tool(
			manager,
			"add_custom_field",
			{"doctype": link, "fieldname": "ai_x", "label": "X", "fieldtype": "Data", "description": "X."},
		)
		permission = self.call_tool(
			manager,
			"set_role_permission",
			{"doctype": link, "role": "AI Test Portal Role", "permissions": {"write": True}},
		)

		for result in (created, updated, deleted, field, permission):
			self.assert_denied(result, "blocked_doctype")

	def test_access_rule_changes_only_through_admin_tools(self):
		manager = self.login(MANAGER)

		created = self.call_tool(
			manager, "create_document", {"doctype": "Access Rule", "data": {"title": "x"}}
		)
		permission = self.call_tool(
			manager,
			"set_role_permission",
			{"doctype": "Access Rule", "role": "AI Test Portal Role", "permissions": {"write": True}},
		)

		self.assert_denied(created, "admin_only")
		self.assert_denied(permission, "blocked_doctype")


class TestCommitsCarryOnlyOwnWrites(YzTestCase):
	def test_denial_log_is_kept_and_a_foreign_pending_write_is_not(self):
		from platform_core.yapay_zeka import access

		set_request(method="POST", path="/api/method/platform_core.api.ai.mcp")
		frappe.local.request_ip = "127.0.0.1"
		marker = frappe.generate_hash(length=12)
		frappe.get_doc(doctype="ToDo", description=marker).insert()
		self.assertTrue(frappe.db.transaction_writes)

		name = access.record_denial("auth", "protocol_error", user=USER_A, principal_type="other")
		frappe.db.rollback()

		self.assertTrue(frappe.db.exists("AI Action Log", name))
		self.assertEqual(frappe.db.count("ToDo", {"description": marker}), 0)

	def test_approval_is_refused_inside_a_transaction_with_pending_writes(self):
		from platform_core.yapay_zeka import access

		frappe.get_doc(doctype="ToDo", description=frappe.generate_hash(length=12)).insert()

		with self.assertRaises(frappe.ValidationError):
			access.require_clean_transaction()
		frappe.db.rollback()
		access.require_clean_transaction()

	def test_no_bare_commit_is_left_in_the_layer(self):
		import re
		from pathlib import Path

		import platform_core

		layer = Path(platform_core.__file__).parent / "yapay_zeka"
		offenders = []
		for path in sorted(layer.rglob("*.py")):
			if "tests" in path.relative_to(layer).parts:
				continue
			for number, line in enumerate(path.read_text().splitlines(), 1):
				if "frappe.db.commit()" in line and "nosemgrep: frappe-request-commit" not in line:
					offenders.append(f"{path.name}:{number}")
				if "nosemgrep" in line and not re.search(r"nosemgrep: [a-z][a-z-]+", line):
					offenders.append(f"{path.name}:{number} names no rule")

		self.assertEqual(offenders, [])


class TestProposalListQuery(YzTestCase):
	def test_list_uses_one_bounded_query_and_never_loads_documents_one_by_one(self):
		from platform_core.yapay_zeka import store

		name = self.make_record(USER_A)
		client = self.login(USER_A)
		ids = [self.propose_update(client, name, title=f"T{i}")["proposal_id"] for i in range(4)]
		frappe.db.set_value(
			"AI Action Proposal", ids[0], "expires_at", add_to_date(now_datetime(), seconds=-5)
		)
		self.human(client, "POST", "reject_proposal", body={"proposal_id": ids[1]})

		with patch.object(store, "load_proposal", side_effect=AssertionError("loaded one by one")):
			everything = self.human(client, "GET", "list_proposals", query={"limit": 3})
			pending = self.human(client, "GET", "list_proposals", query={"status": "pending", "limit": 50})
			expired = self.human(client, "GET", "list_proposals", query={"status": "expired", "limit": 50})
			rejected = self.human(client, "GET", "list_proposals", query={"status": "rejected", "limit": 50})

		self.assertEqual(everything.status_code, 200, everything.get_data(as_text=True))
		self.assertEqual(len(everything.json["message"]["proposals"]), 3)
		listed = lambda response: {row["proposal_id"] for row in response.json["message"]["proposals"]}  # noqa: E731
		self.assertLessEqual({ids[2], ids[3]}, listed(pending))
		self.assertFalse({ids[0], ids[1]} & listed(pending))
		self.assertIn(ids[0], listed(expired))
		self.assertNotIn(ids[2], listed(expired))
		self.assertIn(ids[1], listed(rejected))
		self.assertEqual({row["status"] for row in expired.json["message"]["proposals"]}, {"expired"})


class TestPermissionBypassIsNotLeftBehind(YzTestCase):
	def test_flag_is_restored_after_saving_a_layer_record(self):
		from platform_core.yapay_zeka import store

		doc = store.insert_proposal(
			{"user": USER_A, "tool": "update_document", "status": "pending", "expires_at": now_datetime()}
		)
		after_insert = doc.flags.ignore_permissions
		doc.error = "x"
		store.save_proposal(doc)

		self.assertFalse(after_insert)
		self.assertFalse(doc.flags.ignore_permissions)

	def test_flag_is_restored_when_saving_fails(self):
		from platform_core.yapay_zeka import store

		doc = store.insert_proposal(
			{"user": USER_A, "tool": "update_document", "status": "pending", "expires_at": now_datetime()}
		)
		doc.status = "not-a-status"

		self.assertRaises(frappe.ValidationError, store.save_proposal, doc)
		self.assertFalse(doc.flags.ignore_permissions)


def with_gate(module):
	return patch.dict(sys.modules, {GATE: module})


class TestReportGatePathAndSize(YzTestCase):
	@property
	def arguments(self) -> dict:
		return {"report": REPORT, "filters": {"user": MANAGER, "doctype": DOCTYPE}}

	def gate(self, report_guard=None) -> ModuleType:
		module = ModuleType(GATE)
		if report_guard is not None:
			module.report_guard = report_guard
		return module

	def test_gate_is_called_through_the_public_path_of_the_access_engine(self):
		manager = self.login(MANAGER)
		seen = []

		with with_gate(self.gate(lambda report_name, user=None: seen.append(report_name))):
			result = self.call_tool(manager, "run_report", self.arguments)

		self.assertFalse(result["isError"], result)
		self.assertEqual(seen, [REPORT])

	def test_report_tool_is_closed_when_the_public_function_is_missing(self):
		manager = self.login(MANAGER)

		with with_gate(self.gate()), patch("frappe.desk.query_report.run") as run:
			missing_function = self.call_tool(manager, "run_report", self.arguments)
		with with_gate(None), patch("frappe.desk.query_report.run") as run_again:
			missing_module = self.call_tool(manager, "run_report", self.arguments)

		self.assert_denied(missing_function, "report_gate_unavailable")
		self.assert_denied(missing_module, "report_gate_unavailable")
		run.assert_not_called()
		run_again.assert_not_called()

	def test_layer_does_not_import_private_modules_of_other_modules(self):
		import json
		import re
		from pathlib import Path

		import platform_core

		root = Path(platform_core.__file__).parent
		boundaries = root.parents[2] / "dev" / "modul-sinirlari.json"
		if not boundaries.exists():
			self.skipTest(f"The boundary file is not in this environment: {boundaries}")
		public = {
			path for paths in json.loads(boundaries.read_text())["public_paths"].values() for path in paths
		}
		pattern = re.compile(r"^\s*(?:from|import)\s+(platform_core\.(?!yapay_zeka\b)[\w.]+)", re.MULTILINE)
		offenders = sorted(
			f"{path.name}: {module}"
			for path in [*(root / "yapay_zeka").rglob("*.py"), root / "api" / "ai.py"]
			if "tests" not in path.parts
			for module in pattern.findall(path.read_text())
			if module not in public
		)

		self.assertEqual(offenders, [])

	def test_report_prepared_in_the_background_is_not_run_in_the_request(self):
		self.open_report_gate()
		manager = self.login(MANAGER)
		frappe.db.set_value("Report", REPORT, "prepared_report", 1)
		self.addCleanup(self.restore_report)

		with patch("frappe.desk.query_report.run") as run:
			result = self.call_tool(manager, "run_report", self.arguments)

		self.assert_denied(result, "report_too_large")
		run.assert_not_called()

	def restore_report(self):
		frappe.db.set_value("Report", REPORT, "prepared_report", 0)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

	def test_rows_beyond_the_limit_are_never_copied(self):
		self.open_report_gate()
		manager = self.login(MANAGER)
		touched = []

		class Rows(list):
			def __bool__(self):
				return True

			def __getitem__(self, item):
				raise AssertionError("the whole result was sliced or indexed")

			def __iter__(self):
				for index in range(1000):
					touched.append(index)
					yield {"title": f"row {index}"}

		fake = {"columns": [{"fieldname": "title", "fieldtype": "Data"}], "result": Rows()}
		with patch("frappe.desk.query_report.run", return_value=fake):
			result = self.call_tool(manager, "run_report", {"report": REPORT, "limit": 5})

		self.assertFalse(result["isError"], result)
		self.assertEqual(len(result["structuredContent"]["rows"]), 5)
		self.assertTrue(result["structuredContent"]["truncated"])
		self.assertLessEqual(len(touched), 6)
