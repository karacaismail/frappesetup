"""Rules found by the self-audit against the project's coding standards.

The rule ids are those of `docs/standartlar/`: V-3, V-10, M-1, G-8, G-12, P-1, P-3, A-5, R-7,
H-3, H-10, M-8.
"""

import ast
import json
import re
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.utils import add_days, now_datetime

import platform_core
from platform_core.yapay_zeka.tests import sample_tools_standards as samples
from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, USER_B, YzTestCase

HOOK = "platform_core.yapay_zeka.tests.sample_tools_standards.declare"
APP = Path(platform_core.__file__).parent
LAYER = APP / "yapay_zeka"
CONTRACT = APP.parents[2] / "contracts" / "platform_core-yapay-zeka.openapi.yaml"


def with_tools():
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		return [HOOK] if hook == "ai_tools" else original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


class TestTransactionRules(YzTestCase):
	def test_write_of_a_preview_that_fails_at_approval_is_rolled_back(self):
		"""V-3: a caught error must not leave a half-done write behind."""
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		self.addCleanup(frappe.cache.delete_value, samples.FLAG)

		with with_tools():
			result = self.call_tool(client, "platform_core_writes_in_preview", {"name": name, "title": "New"})
			proposal_id = result["structuredContent"]["proposal_id"]
			digest = self.digest_of(client, proposal_id)
			frappe.cache.set_value(samples.FLAG, 1)
			outcome = self.approve(client, proposal_id, digest).json["message"]

		frappe.db.rollback()
		self.assertEqual((outcome["executed"], outcome["deny_reason"]), (False, "invalid_arguments"))
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")
		self.assertEqual(frappe.db.get_value("AI Action Proposal", proposal_id, "status"), "rejected")

	def test_delete_command_only_counts_unless_told_to_delete(self):
		"""V-10: the count comes first. A call without `dry_run` deletes nothing."""
		from platform_core.yapay_zeka import retention

		manager = self.login(MANAGER)
		self.call_tool(manager, "search_doctypes", {})
		log = self.last_log(tool="search_doctypes").name
		frappe.db.set_value("AI Action Log", log, "creation", add_days(now_datetime(), -400))
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

		frappe.set_user(MANAGER)
		result = retention.purge()

		self.assertTrue(result["dry_run"])
		self.assertTrue(frappe.db.exists("AI Action Log", log))


class TestProposalGuardsItself(YzTestCase):
	"""M-1: the rules of a proposal hold on every write path, not only in the layer's own functions."""

	def proposal(self) -> str:
		name = self.make_record(USER_A)
		return self.propose_update(self.login(USER_A), name, title="New")["proposal_id"]

	def test_approved_content_cannot_change_after_insert(self):
		proposal_id = self.proposal()

		for field, value in (
			("args_json", "{}"),
			("preview_json", "{}"),
			("digest", "0" * 64),
			("preview_digest", "0" * 64),
			("user", USER_B),
			("tool", "delete_document"),
			("target_name", "other"),
		):
			doc = frappe.get_doc("AI Action Proposal", proposal_id)
			doc.set(field, value)
			with self.assertRaises(frappe.PermissionError, msg=field):
				doc.save(
					ignore_permissions=True
				)  # nosemgrep: frappe-ignore-permissions -- the test acts as a system write path

	def test_decided_proposal_cannot_become_pending_again(self):
		proposal_id = self.proposal()
		client = self.login(USER_A)
		self.human(client, "POST", "reject_proposal", body={"proposal_id": proposal_id})

		for status in ("pending", "consumed"):
			doc = frappe.get_doc("AI Action Proposal", proposal_id)
			doc.status = status
			with self.assertRaises(frappe.PermissionError, msg=status):
				doc.save(
					ignore_permissions=True
				)  # nosemgrep: frappe-ignore-permissions -- the test acts as a system write path


class TestInputBounds(YzTestCase):
	"""G-8: every input has an upper bound, and a value over it is refused cleanly."""

	def test_retention_period_has_an_upper_bound(self):
		manager = self.login(MANAGER)

		at_bound = self.human(manager, "POST", "purge_logs", body={"older_than_days": 36500})
		over = self.human(manager, "POST", "purge_logs", body={"older_than_days": 36501})
		huge = self.human(manager, "POST", "purge_logs", body={"older_than_days": 10**12})
		tool = self.call_tool(manager, "purge_action_log", {"older_than_days": 10**12})

		self.assertEqual(at_bound.status_code, 200)
		self.assertEqual((over.status_code, huge.status_code), (417, 417))
		self.assert_denied(tool, "invalid_arguments")

	def test_long_text_and_long_lists_are_refused(self):
		client = self.login(USER_A)
		long_name = "n" * 141

		results = [
			self.call_tool(client, "get_document", {"doctype": DOCTYPE, "name": long_name}),
			self.call_tool(client, "list_documents", {"doctype": DOCTYPE, "fields": ["name"] * 101}),
			self.call_tool(client, "list_documents", {"doctype": DOCTYPE, "order_by": "o" * 141}),
			self.call_tool(
				client, "update_document", {"doctype": DOCTYPE, "name": long_name, "data": {"title": "x"}}
			),
			self.call_tool(client, "get_doctype_schema", {"doctype": "d" * 141}),
		]

		for result in results:
			self.assert_denied(result, "invalid_arguments")

	def test_long_proposal_id_and_digest_are_refused(self):
		client = self.login(USER_A)

		read = self.human(client, "GET", "get_proposal", query={"proposal_id": "p" * 141})
		approve = self.human(
			client, "POST", "approve_proposal", body={"proposal_id": "p", "digest": "d" * 129}
		)

		self.assertEqual((read.status_code, approve.status_code), (417, 417))


class TestSharedRecords(YzTestCase):
	"""G-12: ownership is tested with a shared record too."""

	def test_shared_record_is_read_as_frappe_allows(self):
		name = self.make_record(USER_A, title="Shared")
		client = self.login(USER_B)

		before = self.call_tool(client, "get_document", {"doctype": DOCTYPE, "name": name})
		frappe.share.add(DOCTYPE, name, USER_B, read=1)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		after = self.call_tool(client, "get_document", {"doctype": DOCTYPE, "name": name})
		listed = self.call_tool(client, "list_documents", {"doctype": DOCTYPE, "filters": {"name": name}})
		write = self.call_tool(
			client, "update_document", {"doctype": DOCTYPE, "name": name, "data": {"title": "x"}}
		)

		self.assert_denied(before, "permission")
		self.assertFalse(after["isError"], after)
		self.assertEqual([row["name"] for row in listed["structuredContent"]["documents"]], [name])
		self.assert_denied(write, "permission")

	def test_sharing_a_proposal_gives_the_other_user_nothing(self):
		name = self.make_record(USER_A)
		proposal_id = self.propose_update(self.login(USER_A), name, title="New")["proposal_id"]
		frappe.share.add("AI Action Proposal", proposal_id, USER_B, read=1, write=1)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		other = self.login(USER_B)

		read = self.human(other, "GET", "get_proposal", query={"proposal_id": proposal_id})
		listed = self.human(other, "GET", "list_proposals").json["message"]["proposals"]
		approve = self.human(
			other, "POST", "approve_proposal", body={"proposal_id": proposal_id, "digest": "x"}
		)

		self.assertEqual((read.status_code, approve.status_code), (403, 403))
		self.assertNotIn(proposal_id, [row["proposal_id"] for row in listed])


class TestBoundedQueries(YzTestCase):
	"""P-1 and P-3: one run touches a bounded number of records, and paging has a stable order."""

	def test_one_delete_run_is_bounded_and_says_how_many_wait(self):
		from platform_core.yapay_zeka import retention

		manager = self.login(MANAGER)
		for _ in range(4):
			self.call_tool(manager, "search_doctypes", {})
		frappe.db.rollback()
		table = "AI Action Log"
		for name in frappe.get_all(table, pluck="name"):
			frappe.db.set_value(table, name, "creation", add_days(now_datetime(), -400))
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection
		waiting = frappe.db.count(table)

		with patch.object(retention, "BATCH_SIZE", 3):
			dry = self.human(manager, "POST", "purge_logs", body={}).json["message"]
			first = self.human(manager, "POST", "purge_logs", body={"dry_run": False}).json["message"]

		self.assertGreaterEqual(waiting, 4)
		self.assertEqual((dry["logs"], dry["logs_waiting"]), (3, waiting))
		self.assertEqual((first["logs"], first["logs_waiting"]), (3, waiting))
		frappe.db.rollback()
		# The denied or allowed call rows of this very test may add to the table. Old rows went down by 3.
		old = frappe.db.count(table, {"creation": ("<", add_days(now_datetime(), -365))})
		self.assertEqual(old, waiting - 3)

	def test_pages_with_equal_sort_values_neither_repeat_nor_skip(self):
		names = sorted(self.make_record(USER_A, title="Same") for _ in range(5))
		client = self.login(USER_A)
		base = {"doctype": DOCTYPE, "filters": {"name": ["in", names]}, "limit": 2}

		for order in ("title asc", "title desc", None):
			arguments = {**base, **({"order_by": order} if order else {})}
			seen = []
			for start in (0, 2, 4):
				page = self.call_tool(client, "list_documents", {**arguments, "start": start})
				seen += [row["name"] for row in page["structuredContent"]["documents"]]
			self.assertEqual(sorted(seen), names, order)


class TestStaticStandards(YzTestCase):
	def test_no_function_of_the_tools_exists_only_for_tests(self):
		"""A-5: production code carries no wrapper that only tests call."""
		wrappers = []
		for path in (LAYER / "tools" / "write.py", LAYER / "tools" / "admin.py"):
			for node in ast.walk(ast.parse(path.read_text())):
				if isinstance(node, ast.FunctionDef) and node.name.startswith("run_"):
					wrappers.append(f"{path.name}: {node.name}")

		self.assertEqual(wrappers, [])

	def test_direct_database_reads_live_in_the_store(self):
		"""R-7: the store's docstring says so. The check covers `get_values` too."""
		offenders = []
		for path in sorted(LAYER.rglob("*.py")):
			relative = path.relative_to(LAYER)
			if "tests" in relative.parts or relative.name in ("store.py", "setup.py"):
				continue
			if re.search(
				r"frappe\.db\.(get_values?|get_all|get_list|count|exists|delete|set_value)\(",
				path.read_text(),
			):
				offenders.append(str(relative))

		self.assertEqual(offenders, [])

	def test_doctype_files_have_the_generated_key_order(self):
		"""H-3: a DocType file is in Frappe's export format: sorted keys, one space of indent."""
		for doctype in ("ai_action_log", "ai_action_proposal"):
			path = LAYER / "doctype" / doctype / f"{doctype}.json"
			text = path.read_text()
			self.assertEqual(text, json.dumps(json.loads(text), indent=1, sort_keys=True) + "\n", doctype)

	def test_contract_identifiers_are_english(self):
		"""H-10: tag and security scheme names of the contract are English."""
		import yaml

		self.assertTrue(CONTRACT.exists(), f"The contract must be in the test environment: {CONTRACT}")
		contract = yaml.safe_load(CONTRACT.read_text())

		self.assertEqual([tag["name"] for tag in contract["tags"]], ["mcp", "token", "proposal", "admin"])
		self.assertEqual(sorted(contract["components"]["securitySchemes"]), ["agentToken", "humanSession"])

	def test_every_fixed_user_text_of_the_endpoint_is_translatable(self):
		"""M-8: a text the user reads goes through the translation function."""
		source = (LAYER / "mcp.py").read_text()

		self.assertNotIn('_error("internal_error", "The tool failed', source)
