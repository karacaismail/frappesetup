"""Findings of the independent security review (B1-B6). Each test shows one attack."""

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from platform_core.ai.tests.base import (
	API,
	CHILD_DOCTYPE,
	DESK_USER,
	DOCTYPE,
	MANAGER,
	RESTRICTED_ROLE,
	USER_A,
	USER_B,
	AiTestCase,
)


class TestChildTables(AiTestCase):
	"""B1: a child table write cannot change another record's row or a high-permission field."""

	def row_of(self, parent: str) -> dict:
		return frappe.db.get_value(
			CHILD_DOCTYPE, {"parent": parent}, ["name", "parent", "item"], as_dict=True
		)

	def update(self, client, name: str, rows: list) -> dict:
		return self.call_tool(
			client, "plt_update_document", {"doctype": DOCTYPE, "name": name, "data": {"rows": rows}}
		)

	def test_foreign_row_cannot_be_moved_into_own_document(self):
		mine = self.make_record(USER_A, rows=[{"item": "benim"}])
		theirs = self.make_record(USER_B, rows=[{"item": "onlarin"}])
		foreign = self.row_of(theirs)
		client = self.login(USER_A)

		result = self.update(client, mine, [{"name": foreign.name, "item": "calindi"}])
		if not result["isError"]:
			self.approve(client, result["structuredContent"]["proposal_id"])

		self.assert_denied(result, "invalid_arguments")
		after = self.row_of(theirs)
		self.assertEqual((after.name, after.parent, after.item), (foreign.name, theirs, "onlarin"))

	def test_new_document_cannot_carry_a_row_name(self):
		theirs = self.make_record(USER_B, rows=[{"item": "onlarin"}])
		foreign = self.row_of(theirs)
		client = self.login(USER_A)

		result = self.call_tool(
			client,
			"plt_create_document",
			{
				"doctype": DOCTYPE,
				"data": {"title": "Yeni", "rows": [{"name": foreign.name, "item": "calindi"}]},
			},
		)

		self.assert_denied(result, "invalid_arguments")
		self.assertEqual(self.row_of(theirs).parent, theirs)

	def test_row_field_above_the_users_permlevel_is_rejected_on_create_and_update(self):
		mine = self.make_record(USER_A, rows=[{"item": "benim"}])
		row = self.row_of(mine)
		client = self.login(USER_A)

		created = self.call_tool(
			client,
			"plt_create_document",
			{
				"doctype": DOCTYPE,
				"data": {"title": "Yeni", "rows": [{"item": "x", "locked_note": "yetkisiz"}]},
			},
		)
		updated = self.update(client, mine, [{"name": row.name, "locked_note": "yetkisiz"}])

		self.assert_denied(created, "field_not_permitted")
		self.assert_denied(updated, "field_not_permitted")

	def test_row_cannot_set_its_own_parent_or_system_fields(self):
		mine = self.make_record(USER_A, rows=[{"item": "benim"}])
		theirs = self.make_record(USER_B)
		client = self.login(USER_A)

		for key, value in (
			("parent", theirs),
			("parenttype", DOCTYPE),
			("parentfield", "rows"),
			("owner", USER_B),
			("docstatus", 1),
		):
			result = self.update(client, mine, [{"item": "x", key: value}])
			self.assert_denied(result, "invalid_arguments")

	def test_own_rows_are_kept_changed_and_added_after_approval(self):
		mine = self.make_record(USER_A, rows=[{"item": "bir"}])
		row = self.row_of(mine)
		client = self.login(USER_A)

		proposal = self.update(client, mine, [{"name": row.name, "item": "bir-yeni"}, {"item": "iki"}])
		self.assertFalse(proposal["isError"], proposal)
		outcome = self.approve(client, proposal["structuredContent"]["proposal_id"]).json["message"]

		self.assertTrue(outcome["executed"], outcome)
		rows = frappe.get_all(
			CHILD_DOCTYPE, filters={"parent": mine}, fields=["name", "item"], order_by="idx"
		)
		self.assertEqual([r.item for r in rows], ["bir-yeni", "iki"])
		self.assertEqual(rows[0].name, row.name)
		self.assertEqual(proposal["structuredContent"]["preview"]["changes"][0]["old"][0]["item"], "bir")

	def test_manager_may_write_the_higher_permlevel_row_field(self):
		record = self.make_record(MANAGER)
		manager = self.login(MANAGER)

		proposal = self.update(manager, record, [{"item": "x", "locked_note": "yonetici notu"}])
		self.assertFalse(proposal["isError"], proposal)
		self.assertTrue(
			self.approve(manager, proposal["structuredContent"]["proposal_id"]).json["message"]["executed"]
		)

		self.assertEqual(
			frappe.db.get_value(CHILD_DOCTYPE, {"parent": record}, "locked_note"), "yonetici notu"
		)

	def test_execution_checks_rows_again(self):
		from platform_core.ai.errors import ToolDenied
		from platform_core.ai.tools import write

		mine = self.make_record(USER_A)
		theirs = self.make_record(USER_B, rows=[{"item": "onlarin"}])
		foreign = self.row_of(theirs)
		frappe.set_user(USER_A)

		with self.assertRaises(ToolDenied):
			write.prepare_update(DOCTYPE, mine, {"rows": [{"name": foreign.name, "item": "calindi"}]})
		with self.assertRaises(ToolDenied):
			write.prepare_create(DOCTYPE, {"title": "x", "rows": [{"name": foreign.name}]})


class TestReportSecrets(AiTestCase):
	"""B2: a Password column in report output does not reach the model."""

	COLUMNS = (
		{"fieldname": "title", "label": "Title", "fieldtype": "Data"},
		{"fieldname": "vault_code", "label": "Vault Code", "fieldtype": "Password"},
		{"fieldname": "kasa", "label": "Kasa", "fieldtype": "Password"},
		"Api Key:Data:120",
		"Pin Kodu:Password:120",
	)

	def setUp(self):
		super().setUp()
		self.open_report_gate()

	def run_with(self, rows: list) -> dict:
		manager = self.login(MANAGER)
		fake = {"columns": list(self.COLUMNS), "result": rows}
		with patch("frappe.desk.query_report.run", return_value=fake):
			result = self.call_tool(manager, "plt_run_report", {"report": "Permitted Documents For User"})
		self.assertFalse(result["isError"], result)
		return result

	def test_password_columns_are_removed_from_dict_rows(self):
		result = self.run_with(
			[
				{
					"title": "a",
					"vault_code": "gizli-1",
					"kasa": "gizli-2",
					"api_key": "gizli-3",
					"pin_kodu": "gizli-4",
				}
			]
		)

		self.assertEqual(result["structuredContent"]["rows"], [{"title": "a"}])
		self.assertNotIn("gizli", result["content"][0]["text"])
		self.assertEqual([c["fieldname"] for c in result["structuredContent"]["columns"]], ["title"])

	def test_password_columns_are_removed_from_list_rows(self):
		result = self.run_with([["a", "gizli-1", "gizli-2", "gizli-3", "gizli-4"]])

		self.assertEqual(result["structuredContent"]["rows"], [["a"]])
		self.assertNotIn("gizli", result["content"][0]["text"])

	def test_secret_field_of_the_source_doctype_is_removed_even_if_the_column_hides_its_type(self):
		if not frappe.db.exists("Report", "YZ Test Raporu"):
			frappe.get_doc(
				doctype="Report",
				report_name="YZ Test Raporu",
				ref_doctype=DOCTYPE,
				report_type="Report Builder",
				is_standard="No",
				roles=[{"role": "System Manager"}],
			).insert()
		manager = self.login(MANAGER)
		fake = {
			"columns": [
				{"fieldname": "title", "fieldtype": "Data"},
				{"fieldname": "vault_code", "fieldtype": "Data"},
			],
			"result": [{"title": "a", "vault_code": "gizli-1"}],
		}
		with patch("frappe.desk.query_report.run", return_value=fake):
			result = self.call_tool(manager, "plt_run_report", {"report": "YZ Test Raporu"})

		self.assertFalse(result["isError"], result)
		self.assertEqual(result["structuredContent"]["rows"], [{"title": "a"}])
		self.assertNotIn("gizli", result["content"][0]["text"])


class TestResultState(AiTestCase):
	"""B3: an error that leaves a lasting effect does not count as `failed`."""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in frappe.get_all("Custom Field", filters={"dt": DOCTYPE}, pluck="name"):
			frappe.delete_doc("Custom Field", name, force=True)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		super().tearDown()

	def test_failure_after_a_commit_stays_unknown_and_blocks_the_target(self):
		from platform_core.ai.tools import admin

		manager = self.login(MANAGER)
		arguments = {
			"doctype": DOCTYPE,
			"fieldname": "yz_kalici",
			"label": "Kalici",
			"fieldtype": "Data",
			"description": "Stays after the failure.",
		}
		original = admin.write_custom_field

		def fails_after_writing(*args, **kwargs):
			original(*args, **kwargs)
			raise RuntimeError("Failure after writing")

		proposal = self.call_tool(manager, "plt_add_custom_field", arguments)["structuredContent"]
		second = self.call_tool(manager, "plt_add_custom_field", {**arguments, "label": "Ikinci"})[
			"structuredContent"
		]
		with patch.object(admin, "write_custom_field", fails_after_writing):
			outcome = self.approve(manager, proposal["proposal_id"]).json["message"]
		blocked = self.approve(manager, second["proposal_id"]).json["message"]

		self.assertFalse(outcome["executed"])
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": "yz_kalici"}))
		self.assertEqual(outcome["proposal"]["result"], "unknown")
		self.assertEqual((blocked["executed"], blocked["deny_reason"]), (False, "unresolved_unknown"))

	def test_unknown_is_committed_before_the_handler_runs(self):
		from platform_core.ai.tools import write

		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		original = write.prepare_update
		seen = {}

		def probe(*args, **kwargs):
			# Rollback removes every uncommitted write. What remains is the committed state.
			frappe.db.rollback()
			seen["state"] = frappe.db.get_value("PLT AI Action Proposal", proposal_id, ["status", "result"])
			return original(*args, **kwargs)

		with patch.object(write, "prepare_update", probe):
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertEqual(tuple(seen["state"]), ("consumed", "unknown"))
		self.assertTrue(outcome["executed"], outcome)

	def test_create_with_unknown_result_cannot_be_proposed_again(self):
		client = self.login(USER_A)
		arguments = {"doctype": DOCTYPE, "data": {"title": "Tekrar", "amount": 3}}
		first = self.call_tool(client, "plt_create_document", arguments)["structuredContent"]
		frappe.db.set_value(
			"PLT AI Action Proposal", first["proposal_id"], {"status": "consumed", "result": "unknown"}
		)

		again = self.call_tool(client, "plt_create_document", arguments)

		self.assert_denied(again, "unresolved_unknown")


class TestAdminVersion(AiTestCase):
	"""B4: the admin tool does not overwrite a change that slipped in after the last check."""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in frappe.get_all("Property Setter", filters={"doc_type": DOCTYPE}, pluck="name"):
			frappe.delete_doc("Property Setter", name, force=True)
		frappe.permissions.reset_perms(DOCTYPE)
		frappe.get_doc("User", USER_B).remove_roles("YZ Ek Rol")
		frappe.clear_cache()
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		super().tearDown()

	def approve_with_rival(self, client, proposal_id: str, function_name: str, rival) -> dict:
		"""Inserts another request's committed change right before the execute function."""
		from platform_core.ai.tools import admin

		original = getattr(admin, function_name)

		def raced(*args, **kwargs):
			rival()
			frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
			return original(*args, **kwargs)

		digest = self.digest_of(client, proposal_id)
		with patch.object(admin, function_name, raced):
			return self.approve(client, proposal_id, digest).json["message"]

	def test_field_property_is_not_overwritten(self):
		manager = self.login(MANAGER)
		proposal = self.call_tool(
			manager,
			"plt_set_field_property",
			{"doctype": DOCTYPE, "fieldname": "title", "property": "label", "value": "Onaylanan"},
		)["structuredContent"]

		def rival():
			frappe.make_property_setter(
				{
					"doctype": DOCTYPE,
					"fieldname": "title",
					"property": "label",
					"value": "Rakip",
					"property_type": "Data",
				}
			)

		outcome = self.approve_with_rival(manager, proposal["proposal_id"], "prepare_field_property", rival)
		frappe.clear_cache(doctype=DOCTYPE)

		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("title").label, "Rakip")

	def test_role_permission_is_not_overwritten(self):
		manager = self.login(MANAGER)
		proposal = self.call_tool(
			manager,
			"plt_set_role_permission",
			{"doctype": DOCTYPE, "role": RESTRICTED_ROLE, "permissions": {"delete": False}},
		)["structuredContent"]

		def rival():
			frappe.permissions.update_permission_property(DOCTYPE, RESTRICTED_ROLE, 0, "cancel", 0)

		outcome = self.approve_with_rival(manager, proposal["proposal_id"], "prepare_role_permission", rival)

		self.assertFalse(outcome["executed"], outcome)
		row = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": DOCTYPE, "role": RESTRICTED_ROLE, "permlevel": 0},
			["delete", "cancel"],
		)
		self.assertEqual(tuple(row), (1, 0))

	def test_user_role_is_not_changed_on_a_changed_user(self):
		if not frappe.db.exists("Role", "YZ Ek Rol"):
			frappe.get_doc(doctype="Role", role_name="YZ Ek Rol", desk_access=0).insert()
		manager = self.login(MANAGER)
		proposal = self.call_tool(manager, "plt_assign_role", {"user": USER_B, "role": "YZ Ek Rol"})[
			"structuredContent"
		]

		def rival():
			user = frappe.get_doc("User", USER_B)
			user.bio = "rakip degisiklik"
			user.save(ignore_permissions=True)

		outcome = self.approve_with_rival(manager, proposal["proposal_id"], "prepare_assign_role", rival)
		frappe.clear_cache(user=USER_B)

		self.assertFalse(outcome["executed"], outcome)
		self.assertNotIn("YZ Ek Rol", frappe.get_roles(USER_B))

	def test_generic_update_gets_the_previewed_version_at_execution(self):
		from platform_core.ai.tools import write

		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Onaylanan")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		original = write.prepare_update

		def raced(*args, **kwargs):
			frappe.set_user("Administrator")
			doc = frappe.get_doc(DOCTYPE, name)
			doc.title = "Rakip"
			doc.save()
			frappe.set_user(USER_A)
			frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
			return original(*args, **kwargs)

		with patch.object(write, "prepare_update", raced):
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Rakip")

	def test_permission_preview_shows_the_read_grant_of_a_new_rule(self):
		manager = self.login(MANAGER)
		if not frappe.db.exists("Role", "YZ Ek Rol"):
			frappe.get_doc(doctype="Role", role_name="YZ Ek Rol", desk_access=0).insert()

		proposal = self.call_tool(
			manager,
			"plt_set_role_permission",
			{"doctype": DOCTYPE, "role": "YZ Ek Rol", "permissions": {"print": True}},
		)["structuredContent"]

		changes = {
			change["fieldname"]: (change["old"], change["new"]) for change in proposal["preview"]["changes"]
		}
		self.assertEqual(changes["read"], (0, 1))
		self.assertEqual(changes["print"], (0, 1))

	def test_permissions_of_sensitive_doctypes_and_wide_roles_are_closed(self):
		manager = self.login(MANAGER)

		for doctype in ("Server Script", "User", "Custom DocPerm"):
			result = self.call_tool(
				manager,
				"plt_set_role_permission",
				{"doctype": doctype, "role": RESTRICTED_ROLE, "permissions": {"write": True}},
			)
			self.assert_denied(result, "blocked_doctype")
		wide = self.call_tool(
			manager,
			"plt_set_role_permission",
			{"doctype": DOCTYPE, "role": "Desk User", "permissions": {"read": True}},
		)
		script = self.call_tool(manager, "plt_assign_role", {"user": USER_B, "role": "Script Manager"})

		self.assert_denied(wide, "protected_role")
		self.assert_denied(script, "protected_role")


class TestSessionBoundToken(AiTestCase):
	"""B5: the token of an expired session is rejected. Even if the session row is not deleted."""

	def test_token_of_an_expired_session_is_rejected(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		sid = client.get_cookie("sid").value
		long_ago = add_to_date(now_datetime(), days=-400)
		self.age_session(sid, long_ago)

		still_there = self.session_row_exists(sid)
		response = self.rpc(self.anonymous(), "tools/list", token=token)

		self.assertTrue(still_there)
		self.assertEqual(response.status_code, 401)

	def test_token_of_a_session_past_its_end_is_rejected(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		sid = client.get_cookie("sid").value
		session = frappe.cache.hget("session", sid)
		session["data"]["session_end"] = "2020-01-01T00:00:00+00:00"
		frappe.cache.hset("session", sid, session)

		response = self.rpc(self.anonymous(), "tools/list", token=token)

		self.assertEqual(response.status_code, 401)


class TestHumanCallLog(AiTestCase):
	"""B6: every human call and denial with a known identity is logged."""

	def test_token_issue_is_logged(self):
		client = self.login(USER_A)

		self.issue_token(client)

		log = self.last_log(tool="issue_agent_token", user=USER_A)
		self.assertEqual((log.decision, log.stage, log.principal), ("allowed", "auth", "human_session"))

	def test_reading_and_listing_proposals_leaves_no_log_row(self):
		"""Backlog item 8 changed this rule: a successful GET writes nothing. A denied GET is logged."""
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]

		self.human(client, "GET", "get_proposal", query={"proposal_id": proposal_id})
		self.human(client, "GET", "list_proposals")

		self.assertIsNone(self.last_log(tool="plt_get_proposal", user=USER_A))
		self.assertIsNone(self.last_log(tool="list_proposals", user=USER_A))

	def test_reading_rejecting_and_resolving_another_users_proposal_is_logged(self):
		name = self.make_record(USER_A)
		client_a = self.login(USER_A)
		client_b = self.login(USER_B)
		proposal_id = self.propose_update(client_a, name, title="Yeni")["proposal_id"]

		read = self.human(client_b, "GET", "get_proposal", query={"proposal_id": proposal_id})
		reject = self.human(client_b, "POST", "reject_proposal", body={"proposal_id": proposal_id})
		resolve = self.human(
			client_b, "POST", "resolve_proposal", body={"proposal_id": proposal_id, "outcome": "failed"}
		)
		missing = self.human(client_b, "GET", "get_proposal", query={"proposal_id": "olmayan"})

		self.assertEqual((read.status_code, reject.status_code, resolve.status_code), (403, 403, 403))
		for tool in ("plt_get_proposal", "reject_proposal", "resolve_proposal"):
			log = self.last_log(tool=tool, user=USER_B, proposal=proposal_id)
			self.assertEqual((log.decision, log.deny_reason), ("denied", "not_owner"), tool)
		self.assertEqual(missing.status_code, 404)
		self.assertEqual(
			self.last_log(tool="plt_get_proposal", user=USER_B, deny_reason="not_found").decision, "denied"
		)

	def test_purge_by_a_non_admin_is_logged(self):
		"""A desk user reaches the endpoint. The shell stops a Website User before it, with no log row."""
		client = self.login(DESK_USER)

		response = self.human(client, "POST", "purge_logs", body={})

		self.assertEqual(response.status_code, 403)
		log = self.last_log(tool="purge_logs", user=DESK_USER)
		self.assertEqual((log.decision, log.deny_reason), ("denied", "role_required"))

	def test_rejecting_a_proposal_in_the_wrong_state_is_logged(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		self.human(client, "POST", "reject_proposal", body={"proposal_id": proposal_id})

		again = self.human(client, "POST", "reject_proposal", body={"proposal_id": proposal_id})
		resolve = self.human(
			client, "POST", "resolve_proposal", body={"proposal_id": proposal_id, "outcome": "failed"}
		)

		self.assertEqual((again.status_code, resolve.status_code), (417, 417))
		self.assertEqual(
			self.last_log(tool="reject_proposal", proposal=proposal_id, decision="denied").deny_reason,
			"not_pending",
		)
		self.assertEqual(
			self.last_log(tool="resolve_proposal", proposal=proposal_id, decision="denied").deny_reason,
			"not_pending",
		)

	def test_csrf_header_is_compared_even_when_frappe_skips_its_check(self):
		name = self.make_record(USER_A, title="Eski")
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="Yeni")["proposal_id"]
		digest = self.digest_of(client, proposal_id)
		client.csrf_token = "yanlis"

		# Frappe skips its own check under some settings. That case is set up here.
		with patch("frappe.auth.HTTPRequest.validate_csrf_token", lambda self: None):
			response = self.approve(client, proposal_id, digest)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Eski")

	def test_unknown_tool_calls_spend_the_token_budget(self):
		client = self.login(USER_A)
		token = self.issue_token(client)
		anonymous = self.anonymous()

		for _iteration in range(20):
			self.rpc(anonymous, "tools/call", {"name": "olmayan_arac", "arguments": {}}, token=token)
		response = self.rpc(
			anonymous, "tools/call", {"name": "plt_search_doctypes", "arguments": {}}, token=token
		)

		self.assertEqual(response.status_code, 401)
