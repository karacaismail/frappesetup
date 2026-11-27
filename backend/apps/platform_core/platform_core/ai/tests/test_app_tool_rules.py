"""App tool rules found in the HRMS TR review, and the report gate of the access engine."""

import sys
from types import ModuleType
from unittest.mock import patch

import frappe

from platform_core.ai.tests.base import DOCTYPE, MANAGER, USER_A, AiTestCase, answer_text

HOOK = "platform_core.ai.tests.sample_tools.declare_more"
REPORT = "Permitted Documents For User"
GUARD_MODULE = "platform_core.access.api"


def with_more_tools():
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		return [HOOK] if hook == "ai_tools" else original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


def with_report_guard(guard):
	"""Install a stand-in for the access engine's report gate. `None` makes the import fail."""
	module = None
	if guard is not None:
		module = ModuleType(GUARD_MODULE)
		module.report_guard = guard
	return patch.dict(sys.modules, {GUARD_MODULE: module})


class TestAppToolValidation(AiTestCase):
	def freeze(self, name: str) -> None:
		frappe.db.set_value(DOCTYPE, name, "amount", 99, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit -- test setup, the request reads on another connection

	def test_validation_error_in_preview_is_a_logged_denial(self):
		name = self.make_record(USER_A, title="Old")
		self.freeze(name)
		client = self.login(USER_A)

		with with_more_tools():
			result = self.call_tool(client, "plt_checked_title", {"name": name, "title": "New"})

		self.assert_denied(result, "invalid_arguments")
		# The tool's own text is not returned. It may carry a field value.
		self.assertEqual(
			result["structuredContent"]["error"]["message"], answer_text("The tool refused the input.", USER_A)
		)
		log = self.last_log(tool="plt_checked_title")
		self.assertEqual((log.decision, log.deny_reason), ("denied", "invalid_arguments"))
		self.assertEqual(frappe.db.count("PLT AI Action Proposal", {"target_name": name}), 0)

	def test_validation_error_in_the_approval_preview_rejects_the_proposal(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_more_tools():
			proposal = self.call_tool(client, "plt_checked_title", {"name": name, "title": "New"})
			proposal_id = proposal["structuredContent"]["proposal_id"]
			digest = self.digest_of(client, proposal_id)
			self.freeze(name)
			response = self.approve(client, proposal_id, digest)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		outcome = response.json["message"]
		self.assertEqual((outcome["executed"], outcome["deny_reason"]), (False, "invalid_arguments"))
		self.assertEqual(outcome["proposal"]["status"], "rejected")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")
		log = self.last_log(proposal=proposal_id, stage="approve")
		self.assertEqual((log.decision, log.deny_reason), ("denied", "invalid_arguments"))

	def test_validation_error_in_an_app_tools_own_pre_check_stays_unknown(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		arguments = {"name": name, "title": "refused in pre-check"}

		with with_more_tools():
			proposal = self.call_tool(client, "plt_prepared_title", arguments)["structuredContent"]
			outcome = self.approve(client, proposal["proposal_id"]).json["message"]

		# An app tool's `prepare` is app code, not the layer's own check. Its errors stay unknown.
		self.assertFalse(outcome["executed"])
		self.assertEqual(outcome["proposal"]["result"], "unknown")
		self.assertEqual(outcome["proposal"]["error"], "validation_error")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Old")

	def test_app_tool_with_a_pre_check_executes(self):
		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)

		with with_more_tools():
			proposal = self.call_tool(client, "plt_prepared_title", {"name": name, "title": "New"})
			outcome = self.approve(client, proposal["structuredContent"]["proposal_id"]).json["message"]

		self.assertTrue(outcome["executed"], outcome)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "New")

	def test_versioned_app_tool_is_stopped_by_the_layer_when_the_target_changed(self):
		from platform_core.ai import proposals

		name = self.make_record(USER_A, title="Old")
		client = self.login(USER_A)
		original = proposals._pre_check

		def rival():
			doc = frappe.get_doc(DOCTYPE, name)
			doc.title = "Rival"
			doc.save()

		def rival_then_pre_check(*args, **kwargs):
			# A committed change of another request lands after the last approval check.
			self.in_other_connection(rival)
			return original(*args, **kwargs)

		with with_more_tools():
			proposal = self.call_tool(client, "plt_versioned_title", {"name": name, "title": "New"})
			proposal_id = proposal["structuredContent"]["proposal_id"]
			digest = self.digest_of(client, proposal_id)
			with patch.object(proposals, "_pre_check", rival_then_pre_check):
				outcome = self.approve(client, proposal_id, digest).json["message"]

		self.assertFalse(outcome["executed"], outcome)
		self.assertEqual(
			(outcome["proposal"]["result"], outcome["proposal"]["error"]), ("failed", "document_changed")
		)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "title"), "Rival")


class TestReportGate(AiTestCase):
	@property
	def ARGUMENTS(self) -> dict:
		return {"report": REPORT, "filters": {"user": MANAGER, "doctype": DOCTYPE}}

	def test_report_tool_is_closed_while_the_gate_is_missing(self):
		manager = self.login(MANAGER)

		with with_report_guard(None), patch("frappe.desk.query_report.run") as run:
			result = self.call_tool(manager, "plt_run_report", self.ARGUMENTS)

		self.assert_denied(result, "report_gate_unavailable")
		run.assert_not_called()
		self.assertEqual(self.last_log(tool="plt_run_report").deny_reason, "report_gate_unavailable")

	def test_report_is_not_run_when_the_gate_refuses(self):
		manager = self.login(MANAGER)
		seen = []

		def refuse(report_name, user=None):
			seen.append((report_name, frappe.session.user))
			frappe.throw("The report cannot apply the access rules.", frappe.PermissionError)

		with with_report_guard(refuse), patch("frappe.desk.query_report.run") as run:
			result = self.call_tool(manager, "plt_run_report", self.ARGUMENTS)

		self.assert_denied(result, "permission")
		run.assert_not_called()
		self.assertEqual(seen, [(REPORT, MANAGER)])

	def test_report_runs_when_the_gate_allows(self):
		manager = self.login(MANAGER)

		with with_report_guard(lambda report_name, user=None: None):
			result = self.call_tool(manager, "plt_run_report", self.ARGUMENTS)

		self.assertFalse(result["isError"], result)
		self.assertIn("rows", result["structuredContent"])
