"""The eight items of this layer in `docs/gap-backlog.md`.

1. `expires_at` is ISO 8601 with a UTC offset.
2. Human endpoints answer 401 for an expired session and 403 for no session.
3. A preview is checked against the preview schema before it is stored.
4. `ai_write_closed_doctypes` closes a DocType, and every listed DocType exists on the site.
5. Read results carry `as_of`, `site` and `source`. A proposal carries `created_at`.
6. Read results have a row limit and a byte limit, and say `truncated`.
7. The proposal list is filtered in the database and paginated.
8. A GET request writes to the log only when it is denied.
"""

import json
from datetime import datetime
from unittest.mock import patch

import frappe

from platform_core.yapay_zeka import policy
from platform_core.yapay_zeka.tests.base import CHILD_DOCTYPE, DOCTYPE, MANAGER, USER_A, USER_B, YzTestCase
from platform_core.yapay_zeka.tools import read

# DocTypes of modules that are not merged into this branch yet. A name must leave this set as soon
# as its DocType is installed. The test below fails if it stays.
NOT_INSTALLED_HERE = {"Platform Identity Link", "Access Rule"}


def with_hook(hook_name: str, value: list):
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		return value if hook == hook_name else original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


def aware(value: str) -> datetime:
	"""Parse an ISO 8601 text and insist on a UTC offset."""
	parsed = datetime.fromisoformat(value)
	assert parsed.tzinfo is not None, f"{value!r} carries no UTC offset"
	return parsed


class TestTimesAndProvenance(YzTestCase):
	def test_proposal_times_are_iso_8601_with_an_offset(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)

		opened = self.propose_update(client, name, title="New")
		for_model = self.call_tool(client, "get_proposal", {"proposal_id": opened["proposal_id"]})[
			"structuredContent"
		]
		for_human = self.human(
			client, "GET", "get_proposal", query={"proposal_id": opened["proposal_id"]}
		).json["message"]

		for shape in (opened, for_model, for_human):
			expires, created = aware(shape["expires_at"]), aware(shape["created_at"])
			self.assertEqual(round((expires - created).total_seconds()), 600)
		self.assertEqual(aware(opened["expires_at"]), aware(for_human["expires_at"]))

	def test_read_results_say_when_where_and_from_what(self):
		self.open_report_gate()
		name = self.make_record(MANAGER)
		manager = self.login(MANAGER)
		calls = {
			"search_doctypes": ({"query": "YZ"}, "DocType list"),
			"get_doctype_schema": ({"doctype": DOCTYPE}, f"DocType definition: {DOCTYPE}"),
			"list_documents": ({"doctype": DOCTYPE}, f"DocType: {DOCTYPE}"),
			"get_document": ({"doctype": DOCTYPE, "name": name}, f"DocType: {DOCTYPE}"),
			"run_report": (
				{"report": "Permitted Documents For User", "filters": {"user": MANAGER, "doctype": DOCTYPE}},
				"Report: Permitted Documents For User",
			),
		}

		for tool, (arguments, source) in calls.items():
			result = self.call_tool(manager, tool, arguments)["structuredContent"]
			self.assertEqual((result["site"], result["source"]), (frappe.local.site, source), tool)
			self.assertLess(
				abs((aware(result["as_of"]) - datetime.now().astimezone()).total_seconds()), 120, tool
			)


class TestSessionStatus(YzTestCase):
	def test_expired_session_gets_401_and_no_session_gets_403(self):
		client = self.login(USER_A)
		sid = client.get_cookie("sid").value
		session = frappe.cache.hget("session", sid)
		session["data"]["last_updated"] = "2020-01-01 00:00:00"
		frappe.cache.hset("session", sid, session)
		frappe.db.sql("update `tabSessions` set lastupdate=%s where sid=%s", ("2020-01-01 00:00:00", sid))
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		expired = self.human(client, "GET", "list_proposals")
		expired_post = self.human(client, "POST", "issue_agent_token", body={})
		no_session = self.human(self.anonymous(), "GET", "list_proposals")

		self.assertEqual((expired.status_code, expired_post.status_code), (401, 401))
		self.assertEqual(no_session.status_code, 403)

	def test_contract_states_401_for_every_human_endpoint(self):
		import yaml

		import platform_core

		path = platform_core.__file__
		contract = (
			__import__("pathlib").Path(path).parent.parents[2]
			/ "contracts"
			/ "platform_core-yapay-zeka.openapi.yaml"
		)
		if not contract.exists():
			self.skipTest(f"The contract file is not in this environment: {contract}")
		paths = yaml.safe_load(contract.read_text())["paths"]

		for route, operations in paths.items():
			for operation in operations.values():
				self.assertIn("401", operation["responses"], route)


class TestPreviewSchema(YzTestCase):
	HOOK = "platform_core.yapay_zeka.tests.sample_tools.declare_wrong_preview"

	def test_preview_with_unknown_change_keys_is_refused_before_it_is_stored(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_hook("ai_tools", [self.HOOK]):
			result = self.call_tool(
				client, "platform_core_wrong_preview_keys", {"name": name, "title": "New"}
			)

		self.assert_denied(result, "invalid_preview")
		self.assertEqual(frappe.db.count("AI Action Proposal", {"args_json": ("like", f"%{name}%")}), 0)

	def test_schema_check_names_the_problem(self):
		from platform_core.yapay_zeka import proposals

		good = {"action": "update", "summary": "s", "changes": [{"fieldname": "title", "old": 1, "new": 2}]}
		bad = [
			{"summary": "s", "changes": [{"field": "title", "before": 1, "after": 2}]},
			{"summary": "s", "changes": [{"fieldname": "title"}]},
			{"summary": "s", "changes": "title"},
			{"summary": "s", "details": ["x"]},
			{"summary": "s", "action": "format_disk"},
			{"summary": ""},
		]

		self.assertEqual(proposals.preview_problems(good), [])
		for spec in bad:
			self.assertTrue(proposals.preview_problems(spec), spec)


class TestClosedDoctypeLists(YzTestCase):
	def test_hook_closes_a_doctype_to_generic_write_tools(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		target = {"doctype": DOCTYPE, "name": name}

		with with_hook("ai_write_closed_doctypes", [DOCTYPE]):
			created = self.call_tool(client, "create_document", {"doctype": DOCTYPE, "data": {"title": "x"}})
			updated = self.call_tool(client, "update_document", {**target, "data": {"title": "x"}})
			deleted = self.call_tool(client, "delete_document", target)
			still_reads = self.call_tool(client, "get_document", target)
		opened = self.call_tool(client, "update_document", {**target, "data": {"title": "x"}})

		for result in (created, updated, deleted):
			self.assert_denied(result, "blocked_doctype")
		self.assertFalse(still_reads["isError"], still_reads)
		self.assertFalse(opened["isError"], opened)

	def test_every_doctype_named_by_the_hook_exists_on_this_site(self):
		for doctype in frappe.get_hooks("ai_write_closed_doctypes") or []:
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

	def test_every_doctype_named_in_the_policy_lists_exists_on_this_site(self):
		"""A renamed or removed DocType would silently drop out of a security list."""
		names = set().union(
			policy.CREDENTIAL_DOCTYPES,
			policy.CODE_DOCTYPES,
			policy.ADMIN_DOCTYPES,
			policy.LAYER_DOCTYPES,
			policy.IDENTITY_DOCTYPES,
			policy.FRAMEWORK_OPEN,
		)
		missing = {name for name in names if not frappe.db.exists("DocType", name)}
		installed_meanwhile = {name for name in NOT_INSTALLED_HERE if frappe.db.exists("DocType", name)}

		self.assertEqual(missing - NOT_INSTALLED_HERE, set())
		self.assertEqual(installed_meanwhile, set())
		self.assertGreater(len(names), 60)


class TestReadLimits(YzTestCase):
	def test_document_with_many_rows_is_cut_and_says_so(self):
		rows = [{"item": f"row {index}"} for index in range(read.MAX_CHILD_ROWS + 25)]
		name = self.make_record(USER_A, rows=rows)
		client = self.login(USER_A)

		result = self.call_tool(client, "get_document", {"doctype": DOCTYPE, "name": name})[
			"structuredContent"
		]
		small = self.call_tool(
			client,
			"get_document",
			{"doctype": DOCTYPE, "name": self.make_record(USER_A, rows=[{"item": "one"}])},
		)["structuredContent"]

		self.assertEqual(len(result["document"]["rows"]), read.MAX_CHILD_ROWS)
		self.assertTrue(result["truncated"])
		self.assertFalse(small["truncated"])
		self.assertEqual(frappe.db.count(CHILD_DOCTYPE, {"parent": name}), read.MAX_CHILD_ROWS + 25)

	def test_result_over_the_byte_limit_is_cut_and_says_so(self):
		big = "x" * 4000
		names = [
			self.make_record(USER_A, title=f"{index:02d} {big}"[:140], access_token="") for index in range(6)
		]
		client = self.login(USER_A)

		with patch.object(read, "MAX_RESULT_BYTES", 600):
			listed = self.call_tool(
				client, "list_documents", {"doctype": DOCTYPE, "fields": ["name", "title"]}
			)
		with patch.object(read, "MAX_RESULT_BYTES", 150):
			one = self.call_tool(client, "get_document", {"doctype": DOCTYPE, "name": names[0]})

		for result in (listed, one):
			self.assertFalse(result["isError"], result)
			self.assertTrue(result["structuredContent"]["truncated"])
		kept = listed["structuredContent"]["documents"]
		self.assertLess(len(kept), 6)
		self.assertTrue(listed["structuredContent"]["has_next_page"])
		self.assertLessEqual(len(json.dumps(kept)), 600)
		self.assertLessEqual(len(json.dumps(one["structuredContent"]["document"])), 150)
		self.assertEqual(one["structuredContent"]["document"]["name"], names[0])

	def test_report_result_over_the_byte_limit_is_cut(self):
		self.open_report_gate()
		manager = self.login(MANAGER)
		fake = {
			"columns": [{"fieldname": "title", "fieldtype": "Data"}],
			"result": [{"title": "y" * 200} for _ in range(50)],
		}

		with (
			patch("frappe.desk.query_report.run", return_value=fake),
			patch.object(read, "MAX_RESULT_BYTES", 1000),
		):
			result = self.call_tool(manager, "run_report", {"report": "Permitted Documents For User"})

		rows = result["structuredContent"]["rows"]
		self.assertTrue(result["structuredContent"]["truncated"])
		self.assertLess(len(rows), 50)
		self.assertLessEqual(len(json.dumps(rows)), 1000)


class TestProposalPages(YzTestCase):
	def test_list_is_paginated_and_reaches_old_proposals(self):
		name = self.make_record(USER_B)
		client = self.login(USER_B)
		ids = [self.propose_update(client, name, title=f"T{index}")["proposal_id"] for index in range(5)]

		first = self.human(client, "GET", "list_proposals", query={"limit": 2}).json["message"]
		second = self.human(client, "GET", "list_proposals", query={"limit": 2, "start": 2}).json["message"]
		third = self.human(
			client, "GET", "list_proposals", query={"limit": 2, "start": 4, "status": "pending"}
		).json["message"]
		far = self.human(client, "GET", "list_proposals", query={"limit": 2, "start": 100000}).json["message"]

		page = lambda body: [row["proposal_id"] for row in body["proposals"]]  # noqa: E731
		self.assertEqual(page(first), [ids[4], ids[3]])
		self.assertEqual(page(second), [ids[2], ids[1]])
		self.assertEqual(page(third)[:1], [ids[0]])
		self.assertEqual((first["has_next_page"], second["has_next_page"]), (True, True))
		self.assertEqual((page(far), far["has_next_page"]), ([], False))

	def test_negative_start_is_refused(self):
		client = self.login(USER_A)

		response = self.human(client, "GET", "list_proposals", query={"start": -1})

		self.assertEqual(response.status_code, 417)


class TestGetWritesOnlyDenials(YzTestCase):
	def test_allowed_get_requests_write_nothing(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)
		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]
		before = frappe.db.count("AI Action Log")

		self.human(client, "GET", "get_proposal", query={"proposal_id": proposal_id})
		self.human(client, "GET", "list_proposals")

		self.assertEqual(frappe.db.count("AI Action Log"), before)

	def test_denied_get_request_is_still_logged(self):
		name = self.make_record(USER_A)
		proposal_id = self.propose_update(self.login(USER_A), name, title="New")["proposal_id"]

		response = self.human(self.login(USER_B), "GET", "get_proposal", query={"proposal_id": proposal_id})

		self.assertEqual(response.status_code, 403)
		log = self.last_log(tool="get_proposal", user=USER_B, proposal=proposal_id)
		self.assertEqual((log.decision, log.deny_reason), ("denied", "not_owner"))
