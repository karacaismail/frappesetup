"""Rules decided after the fourth independent review.

Blocker: an approval is valid only for the preview the human saw. The server previews again and
compares the whole preview and the target with what it stored. A difference stops the execution
with `document_changed`, and a new proposal with a new human approval is needed.
Major 1: a stored preview follows the published preview schema exactly.
Major 2 and 3: the byte limit covers the whole result, and a cut list says where to continue.
Major 4: model names stay out of the layer's code.
Minor: the start of the proposal list has an upper bound.
"""

import hashlib
import json
import re
from pathlib import Path
from unittest.mock import patch

import frappe

import platform_core
from platform_core.ai.tests import sample_tools_review4 as samples
from platform_core.ai.tests.base import DOCTYPE, MANAGER, USER_A, AiTestCase
from platform_core.ai.tools import read

HOOK = "platform_core.ai.tests.sample_tools_review4.declare"
LAYER = Path(platform_core.__file__).parent / "ai"

# SHA-256 of the lower-case names of model families. The names themselves are not written here,
# so this file does not trip the rule it enforces.
MODEL_FAMILY_HASHES = frozenset(
	{
		"c857d09db23e6822e3600bc06ad8d58f92ed62bc8efd81c753f77048662cb97d",
		"6f7ac1823da81d2e52d1a1549ee69c85bbf8bb56d06682849e7c09da2785ce3b",
		"5d72436256ada53828b51895a94bb8489e9f1ac4fe937a8024ef1594e7045ff6",
		"053ea4804ef1bb33d4a3d6fb024a614b6d257cebc2bc7cd915da9c9522f37ffc",
		"fc5a1047f5919892fcdf8aa79ea5d6bb6531b5c176939ef0110906cb225941c1",
		"920510199770f4d65cb8aaa2cd12bdb2b8c37f5b3907c50a734a0e3409da2823",
		"c97504235ab15009f6c5f11ba890007a5f3fdd20c9e57b53ea74855033572ddf",
		"67f2d22514622d1be30c14ee9f3cb104503a159a33a656ca91a1953aa9616429",
	}
)


def with_tools():
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		return [HOOK] if hook == "ai_tools" else original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


class TestApprovalCoversTheWholePreview(AiTestCase):
	def setUp(self):
		super().setUp()
		frappe.cache.delete_value(samples.PRICE_KEY)
		frappe.cache.delete_value(samples.TARGET_KEY)
		self.addCleanup(frappe.cache.delete_value, samples.PRICE_KEY)
		self.addCleanup(frappe.cache.delete_value, samples.TARGET_KEY)

	def propose(self, client, tool: str, name: str) -> tuple[str, str]:
		result = self.call_tool(client, tool, {"name": name, "title": "New"})
		self.assertFalse(result["isError"], result)
		proposal_id = result["structuredContent"]["proposal_id"]
		return proposal_id, self.digest_of(client, proposal_id)

	def assert_stopped(self, outcome: dict, name: str) -> None:
		self.assertEqual((outcome["executed"], outcome["deny_reason"]), (False, "document_changed"), outcome)
		self.assertEqual(outcome["proposal"]["status"], "rejected")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_changed_preview_of_an_unversioned_tool_stops_the_approval(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_tools():
			proposal_id, digest = self.propose(client, "plt_priced", name)
			frappe.cache.set_value(samples.PRICE_KEY, 900)
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assert_stopped(outcome, name)
		log = self.last_log(proposal=proposal_id, stage="approve")
		self.assertEqual((log.decision, log.deny_reason), ("denied", "document_changed"))

	def test_changed_preview_of_a_versioned_tool_stops_the_approval(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_tools():
			proposal_id, digest = self.propose(client, "plt_priced_versioned", name)
			frappe.cache.set_value(samples.PRICE_KEY, 900)
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assert_stopped(outcome, name)

	def test_changed_target_of_a_versioned_tool_stops_the_approval(self):
		name = self.make_record(USER_A, title="Old")
		other = self.make_record(USER_A, title="Other")
		client = self.login(USER_A)

		with with_tools():
			proposal_id, digest = self.propose(client, "plt_priced_versioned", name)
			frappe.cache.set_value(samples.TARGET_KEY, other)
			outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assert_stopped(outcome, name)

	def test_unchanged_preview_is_approved(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_tools():
			for tool in ("plt_priced", "plt_priced_versioned"):
				frappe.db.set_value(DOCTYPE, name, "title", "Old")
				proposal_id, digest = self.propose(client, tool, name)
				outcome = self.approve(client, proposal_id, digest).json["message"]
				self.assertTrue(outcome["executed"], outcome)

	def test_preview_that_changes_between_approval_check_and_execution_is_stopped(self):
		"""The last check runs in the layer's own pre-check, under the target lock for a versioned tool."""
		from platform_core.ai import proposals

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		original = proposals._pre_check

		def price_moves_then_pre_check(*args, **kwargs):
			frappe.cache.set_value(samples.PRICE_KEY, 900)
			return original(*args, **kwargs)

		with with_tools():
			for tool in ("plt_priced", "plt_priced_versioned"):
				frappe.cache.delete_value(samples.PRICE_KEY)
				proposal_id, digest = self.propose(client, tool, name)
				with patch.object(proposals, "_pre_check", price_moves_then_pre_check):
					outcome = self.approve(client, proposal_id, digest).json["message"]
				self.assertFalse(outcome["executed"], (tool, outcome))
				self.assertEqual(
					(outcome["proposal"]["result"], outcome["proposal"]["error"]),
					("failed", "document_changed"),
					tool,
				)
				self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_stale_read_after_the_lock_cannot_hide_a_changed_target(self):
		"""Under repeatable read an unlocked read after the lock may still see the old row.

		The tool's preview is made to answer from the old snapshot. The layer's own locked read of
		the target row sees the change, so the approval stops.
		"""
		from platform_core.ai import proposals, store

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		original = proposals._pre_check
		old_stamp = store.row_stamp(DOCTYPE, name)

		def rival():
			frappe.db.set_value(DOCTYPE, name, "amount", 77)

		with with_tools():
			proposal_id, digest = self.propose(client, "plt_priced_versioned", name)
			stale = samples.preview_priced_versioned(name, "New")

			def target_moves_then_pre_check(*args, **kwargs):
				self.in_other_connection(rival)
				# Every unlocked read in the pre-check answers from the old snapshot.
				with patch.object(store, "row_stamp", lambda doctype, row: old_stamp):
					return original(*args, **kwargs)

			with (
				patch.object(samples, "preview_priced_versioned", lambda name, title: dict(stale)),
				patch.object(proposals, "_pre_check", target_moves_then_pre_check),
			):
				outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"], outcome)
		self.assertIn("document_changed", (outcome["deny_reason"], outcome["proposal"]["error"]))
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_row_stamp_at_execution_comes_from_a_locking_read(self):
		from platform_core.ai import store

		name = self.make_record(USER_A, title="Old")
		reads = []
		original = frappe.db.get_value

		def spy(*args, **kwargs):
			reads.append(kwargs.get("for_update"))
			return original(*args, **kwargs)

		with patch.object(frappe.db, "get_value", spy):
			stamp = store.locked_row_stamp(DOCTYPE, name)

		self.assertEqual(reads, [True])
		self.assertEqual(stamp, str(frappe.db.get_value(DOCTYPE, name, "modified")))
		self.assertIsNone(store.locked_row_stamp(DOCTYPE, "no-such-row"))

	def test_versioned_tool_locks_the_stored_target(self):
		from platform_core.ai import proposals, store

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		locked = []
		original = store.locked_row_stamp

		def spy(doctype, row):
			locked.append((doctype, row))
			return original(doctype, row)

		with with_tools(), patch.object(store, "locked_row_stamp", spy):
			proposal_id, digest = self.propose(client, "plt_priced_versioned", name)
			self.assertTrue(self.approve(client, proposal_id, digest).json["message"]["executed"])

		self.assertEqual(locked, [(DOCTYPE, name)])

	def test_proposal_stores_a_digest_of_the_whole_preview(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		proposal_id = self.propose_update(client, name, title="New")["proposal_id"]

		stored = frappe.db.get_value("PLT AI Action Proposal", proposal_id, "preview_digest")
		self.assertRegex(stored or "", r"^[0-9a-f]{64}$")
		self.assertTrue(frappe.get_meta("PLT AI Action Proposal").get_field("preview_digest").description)


class TestPreviewFollowsTheSchema(AiTestCase):
	def test_label_of_the_wrong_type_opens_no_proposal(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_tools():
			result = self.call_tool(client, "plt_numeric_label", {"name": name, "title": "New"})

		self.assert_denied(result, "invalid_preview")
		self.assertEqual(frappe.db.count("PLT AI Action Proposal", {"args_json": ("like", f"%{name}%")}), 0)

	def test_preview_is_checked_against_the_published_schema(self):
		from platform_core.ai import proposals

		good = {
			"action": "update",
			"summary": "s",
			"changes": [{"fieldname": "t", "label": None, "old": 1, "new": 2}],
		}
		bad = [
			{"summary": "s", "changes": [{"fieldname": "t", "label": 5, "new": 2}]},
			{"summary": "s", "changes": [{"fieldname": 7, "new": 2}]},
			{"summary": 3},
			{"summary": "s", "details": "text"},
		]

		self.assertEqual(proposals.preview_problems(good), [])
		for spec in bad:
			self.assertTrue(proposals.preview_problems(spec), spec)


class TestByteLimitCoversTheWholeResult(AiTestCase):
	def test_report_columns_count_toward_the_limit(self):
		self.open_report_gate()
		manager = self.login(MANAGER)
		columns = [{"fieldname": f"c{index}", "label": "L" * 100, "fieldtype": "Data"} for index in range(20)]
		fake = {"columns": columns, "result": [{f"c{index}": "v" for index in range(20)} for _ in range(30)]}

		with (
			patch("frappe.desk.query_report.run", return_value=fake),
			patch.object(read, "MAX_RESULT_BYTES", 4000),
		):
			some = self.call_tool(manager, "plt_run_report", {"report": "Permitted Documents For User"})
		with (
			patch("frappe.desk.query_report.run", return_value=fake),
			patch.object(read, "MAX_RESULT_BYTES", 1000),
		):
			none = self.call_tool(manager, "plt_run_report", {"report": "Permitted Documents For User"})

		for result, limit in ((some, 4000), (none, 1000)):
			body = result["structuredContent"]
			self.assertTrue(body["truncated"], limit)
			self.assertLessEqual(len(json.dumps({"columns": body["columns"], "rows": body["rows"]})), limit)
		self.assertEqual(len(some["structuredContent"]["columns"]), 20)
		self.assertLess(len(some["structuredContent"]["rows"]), 30)
		self.assertEqual((none["structuredContent"]["columns"], none["structuredContent"]["rows"]), ([], []))

	def test_doctype_schema_is_cut_and_says_so(self):
		from platform_core.ai.tools import definition

		client = self.login(USER_A)

		whole = self.call_tool(client, "plt_get_doctype_schema", {"doctype": DOCTYPE})["structuredContent"]
		with patch.object(definition, "MAX_RESULT_BYTES", 600):
			cut = self.call_tool(client, "plt_get_doctype_schema", {"doctype": DOCTYPE})["structuredContent"]

		self.assertFalse(whole["truncated"])
		self.assertTrue(cut["truncated"])
		self.assertLess(len(cut["fields"]), len(whole["fields"]))
		self.assertLessEqual(len(json.dumps(cut["fields"])), 600)

	def test_cut_list_says_where_to_continue_and_never_stalls(self):
		names = sorted(self.make_record(USER_A, title=f"{index} " + "x" * 120) for index in range(5))
		client = self.login(USER_A)
		arguments = {
			"doctype": DOCTYPE,
			"fields": ["name", "title"],
			"order_by": "name asc",
			"filters": {"name": ["in", names]},
		}

		seen, start, rounds = [], 0, 0
		with patch.object(read, "MAX_RESULT_BYTES", 350):
			while start is not None and rounds < 10:
				page = self.call_tool(client, "plt_list_documents", {**arguments, "start": start})[
					"structuredContent"
				]
				seen += [row["name"] for row in page["documents"]]
				self.assertEqual(page["has_next_page"], page["next_start"] is not None)
				if page["next_start"] is not None:
					self.assertGreater(page["next_start"], start)
				start, rounds = page["next_start"], rounds + 1

		self.assertEqual(seen, names)
		self.assertGreater(rounds, 1)

	def test_record_too_big_for_the_limit_is_returned_cut_instead_of_an_empty_page(self):
		name = self.make_record(USER_A, title="y" * 130)
		client = self.login(USER_A)
		arguments = {
			"doctype": DOCTYPE,
			"fields": ["name", "title", "owner", "creation"],
			"filters": {"name": name},
		}

		with patch.object(read, "MAX_RESULT_BYTES", 60):
			page = self.call_tool(client, "plt_list_documents", arguments)["structuredContent"]

		self.assertEqual([row["name"] for row in page["documents"]], [name])
		self.assertTrue(page["truncated"])
		self.assertEqual((page["has_next_page"], page["next_start"]), (False, None))

	def test_uncut_list_has_no_next_start_on_the_last_page(self):
		name = self.make_record(USER_A)
		client = self.login(USER_A)

		page = self.call_tool(client, "plt_list_documents", {"doctype": DOCTYPE, "filters": {"name": name}})[
			"structuredContent"
		]

		self.assertEqual((page["truncated"], page["has_next_page"], page["next_start"]), (False, False, None))


class TestSmallRules(AiTestCase):
	def test_start_of_the_proposal_list_has_an_upper_bound(self):
		client = self.login(USER_A)

		at_bound = self.human(client, "GET", "list_proposals", query={"start": 10000})
		over = self.human(client, "GET", "list_proposals", query={"start": 10001})
		huge = self.human(client, "GET", "list_proposals", query={"start": 10**30})

		self.assertEqual(at_bound.status_code, 200)
		self.assertEqual((over.status_code, huge.status_code), (417, 417))

	def test_no_model_family_name_in_the_layer(self):
		"""Kept until the project's AI readiness gate runs on every merge. The gate has the same rule."""
		offenders = []
		files = [*LAYER.rglob("*.py"), *LAYER.rglob("*.json"), LAYER.parent / "api" / "ai.py"]
		for path in sorted(files):
			# A model name is a family name followed by a version, such as a digit or a dash and a word.
			for token in set(
				re.findall(r"(?<![a-z_])([a-z]+)(?=[-:.]?\d|-[a-z0-9])", path.read_text().lower())
			):
				if hashlib.sha256(token.encode()).hexdigest() in MODEL_FAMILY_HASHES:
					offenders.append(f"{path.name}: a model family name")

		self.assertEqual(offenders, [])
		self.assertEqual(len(MODEL_FAMILY_HASHES), 8)
