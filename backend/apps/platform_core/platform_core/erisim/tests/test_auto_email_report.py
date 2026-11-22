"""Auto Email Report on governed data.

The record runs a report later, without the user being present, and mails the result. The
project runs no scheduled jobs (D-6), so the rule is as narrow as it can be:

- Only a System Manager may create, change, download or send a record that touches governed
  data. The check looks at the record's new report and at the report it had before.
- The report rules also hold for the user named on the record.
- A record runs only while a System Manager's approval is on file. Saving the record by hand
  is the approval. It keeps who approved and when. A record changed after its approval, or
  saved before the rule existed, does not run, whoever starts it. That includes the scheduler,
  which works as Administrator.
- Installing and migrating switch off every such record that has no valid approval.
"""

from unittest.mock import patch

import frappe
from frappe.core.doctype.report.report import Report
from frappe.email.doctype.auto_email_report import auto_email_report
from frappe.utils.background_jobs import execute_job

from platform_core.erisim import reports
from platform_core.erisim.tests.base import ADMIN, DOCTYPE, EMPLOYEE_1, HR, MANAGER_1, ErisimTestCase
from platform_core.erisim.tests.test_report_rules import (
	BUILDER_REPORT,
	FREE_BUILDER_REPORT,
	NAME_REPORT,
	SALARY,
	SCRIPT_REPORT,
	ensure_reports,
)

RECORD = "Auto Email Report"
APPROVAL = "Auto Email Report Approval"
REPORT_MANAGER = "Report Manager"
SCHEDULER_JOB = "frappe.email.doctype.auto_email_report.auto_email_report.process_auto_email_report"


class AutoEmailReportTestCase(ErisimTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_reports()

	def setUp(self):
		super().setUp()
		self.addCleanup(self.cleanup)
		# Frappe lets this role create and change Auto Email Reports. It is not a System Manager.
		frappe.get_doc("User", HR).add_roles(REPORT_MANAGER)
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		if hasattr(frappe.local, "job"):
			del frappe.local.job
		frappe.get_doc("User", HR).remove_roles(REPORT_MANAGER)
		frappe.db.delete(RECORD)
		frappe.db.delete(APPROVAL)
		frappe.db.commit()  # nosemgrep

	def auto_report(self, report: str, user: str, report_type: str = "Report Builder", **values):
		return frappe.get_doc(
			doctype=RECORD,
			report=report,
			report_type=report_type,
			user=user,
			enabled=1,
			email_to="ar.reader@example.test",
			format="CSV",
			frequency="Daily",
			**values,
		)

	def legacy(self, report: str, user: str = ADMIN, report_type: str = "Report Builder") -> str:
		"""A record saved before the rule existed: written without any check and never approved."""
		doc = self.auto_report(report, user, report_type)
		doc.name = f"{report} {user}"
		doc.db_insert()
		frappe.db.commit()  # nosemgrep: the request uses another connection
		return doc.name

	def approved(self, report: str, user: str = ADMIN, report_type: str = "Report Builder", **values) -> str:
		"""A record a System Manager saved by hand."""
		frappe.set_user(ADMIN)
		try:
			name = self.auto_report(report, user, report_type, **values).insert().name
		finally:
			frappe.set_user("Administrator")
		frappe.db.commit()  # nosemgrep: the request uses another connection
		return name

	def gate_refuses(self, doc, caller: str) -> bool:
		"""Only the gate's refusal counts. Frappe's own validation of the record is not under test."""
		frappe.set_user(caller)
		try:
			doc.validate()
		except frappe.PermissionError:
			return True
		except frappe.ValidationError:
			return False
		finally:
			frappe.set_user("Administrator")
		return False

	def run_scheduler_job(self, name: str) -> None:
		"""Process the record the way the scheduler's worker does: as Administrator."""
		execute_job(
			frappe.local.site,
			SCHEDULER_JOB,
			None,
			"ar-test-auto-email-report",
			{"report": frappe._dict(name=name)},
			user="Administrator",
			is_async=False,
		)


class TestWhoMaySaveAndRun(AutoEmailReportTestCase):
	def test_report_manager_cannot_save_one_that_runs_as_a_system_manager(self):
		"""Picking a more powerful account must not open the report."""
		for report, report_type in (
			(NAME_REPORT, "Query Report"),
			(SCRIPT_REPORT, "Script Report"),
			(BUILDER_REPORT, "Report Builder"),
		):
			with self.subTest(report=report):
				self.assertTrue(self.gate_refuses(self.auto_report(report, ADMIN, report_type), HR))
		frappe.set_user(HR)
		self.assertRaises(frappe.PermissionError, self.auto_report(BUILDER_REPORT, ADMIN).insert)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.count(RECORD))

	def test_system_manager_may_save_one(self):
		for report, report_type in ((NAME_REPORT, "Query Report"), (BUILDER_REPORT, "Report Builder")):
			with self.subTest(report=report):
				self.assertFalse(self.gate_refuses(self.auto_report(report, ADMIN, report_type), ADMIN))

	def test_record_user_must_pass_the_report_rule_too(self):
		"""A System Manager cannot schedule a query report to run for a narrowed user."""
		for user in (EMPLOYEE_1, MANAGER_1, HR):
			with self.subTest(user=user):
				self.assertTrue(self.gate_refuses(self.auto_report(NAME_REPORT, user, "Query Report"), ADMIN))
				self.assertTrue(
					self.gate_refuses(self.auto_report(SCRIPT_REPORT, user, "Script Report"), ADMIN)
				)

	def test_report_manager_cannot_change_download_or_send_an_existing_record(self):
		name = self.approved(BUILDER_REPORT)
		frappe.set_user(HR)
		doc = frappe.get_doc(RECORD, name)

		self.assertRaises(frappe.PermissionError, doc.save)
		self.assertRaises(frappe.PermissionError, auto_email_report.download, name)
		self.assertRaises(frappe.PermissionError, auto_email_report.send_now, name)
		self.assertRaises(frappe.PermissionError, doc.send)
		self.assertRaises(frappe.PermissionError, doc.get_report_content)

	def test_report_manager_is_left_alone_on_ungoverned_data(self):
		doc = self.auto_report(FREE_BUILDER_REPORT, HR)

		self.assertFalse(self.gate_refuses(doc, HR))


class TestPreviousReport(AutoEmailReportTestCase):
	"""Review O1: moving a record away from a governed report is a change to a governed record."""

	def test_report_manager_cannot_move_a_record_to_an_ungoverned_report(self):
		name = self.approved(BUILDER_REPORT)
		frappe.set_user(HR)
		doc = frappe.get_doc(RECORD, name)
		doc.report = FREE_BUILDER_REPORT

		self.assertRaises(frappe.PermissionError, doc.save)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(RECORD, name, "report"), BUILDER_REPORT)

	def test_same_change_is_refused_over_both_rest_apis(self):
		name = self.approved(BUILDER_REPORT)
		client = self.login(HR)
		body = {"report": FREE_BUILDER_REPORT, "email_to": "ar.other@example.test"}

		version_1 = self.send(client, "PUT", f"/api/resource/{RECORD}/{name}", body=body)
		version_2 = self.send(client, "PUT", f"/api/v2/document/{RECORD}/{name}", body=body)

		for response in (version_1, version_2):
			self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertEqual(
			frappe.db.get_value(RECORD, name, ["report", "email_to"]),
			(BUILDER_REPORT, "ar.reader@example.test"),
		)

	def test_system_manager_may_move_the_record(self):
		name = self.approved(BUILDER_REPORT)
		frappe.set_user(ADMIN)
		doc = frappe.get_doc(RECORD, name)
		doc.report = FREE_BUILDER_REPORT

		doc.save()

		self.assertEqual(frappe.db.get_value(RECORD, name, "report"), FREE_BUILDER_REPORT)


class TestApproval(AutoEmailReportTestCase):
	"""Review E1: an old record must not run on the scheduler's Administrator session."""

	def assert_not_run(self, name: str) -> None:
		"""The scheduler job ends without running the report and without queueing an email."""
		before = frappe.db.count("Email Queue")
		with patch.object(Report, "get_data") as get_data, patch.object(frappe, "sendmail") as sendmail:
			self.run_scheduler_job(name)
		get_data.assert_not_called()
		sendmail.assert_not_called()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Email Queue"), before)

	def test_scheduler_refuses_a_record_saved_before_the_rule(self):
		"""A Report Manager once saved it for a System Manager. Nobody approved it."""
		self.assert_not_run(self.legacy(BUILDER_REPORT))
		self.assert_not_run(self.legacy(NAME_REPORT, report_type="Query Report"))

	def test_unapproved_record_cannot_be_run_by_hand_either(self):
		name = self.legacy(BUILDER_REPORT)

		for caller in (ADMIN, "Administrator"):
			with self.subTest(caller=caller):
				frappe.set_user(caller)
				self.assertRaises(frappe.PermissionError, auto_email_report.download, name)
				self.assertRaises(frappe.PermissionError, auto_email_report.send_now, name)
				frappe.set_user("Administrator")

	def test_saving_by_a_system_manager_records_who_approved_and_when(self):
		name = self.approved(BUILDER_REPORT)

		approval = frappe.db.get_value(
			APPROVAL, name, ["approved_by", "approved_on", "settings_digest"], as_dict=True
		)

		self.assertEqual(approval.approved_by, ADMIN)
		self.assertTrue(approval.approved_on)
		self.assertEqual(len(approval.settings_digest), 64)

	def test_scheduler_runs_an_approved_record(self):
		name = self.approved(BUILDER_REPORT)

		with patch.object(Report, "get_data", return_value=([], [])) as get_data:
			self.run_scheduler_job(name)

		get_data.assert_called_once()

	def test_record_changed_after_its_approval_does_not_run(self):
		"""The recipients change without a System Manager saving the record."""
		name = self.approved(BUILDER_REPORT)
		frappe.db.set_value(RECORD, name, "email_to", "ar.stranger@example.test", update_modified=False)
		frappe.db.commit()  # nosemgrep: the job reads committed data

		self.assert_not_run(name)

	def test_saving_again_renews_the_approval(self):
		name = self.approved(BUILDER_REPORT)
		frappe.set_user(ADMIN)
		doc = frappe.get_doc(RECORD, name)
		doc.email_to = "ar.second@example.test"
		doc.save()
		frappe.set_user("Administrator")
		frappe.db.commit()  # nosemgrep

		with patch.object(Report, "get_data", return_value=([], [])) as get_data:
			self.run_scheduler_job(name)

		get_data.assert_called_once()

	def test_a_job_cannot_approve(self):
		"""Only a save by hand approves. A save inside a background job does not."""
		name = self.legacy(BUILDER_REPORT)
		frappe.local.job = frappe._dict(method="some.app.job", kwargs={})
		frappe.get_doc(RECORD, name).save()
		del frappe.local.job

		self.assertFalse(frappe.db.exists(APPROVAL, name))

	def test_record_on_ungoverned_data_needs_no_approval(self):
		name = self.legacy(FREE_BUILDER_REPORT)

		with patch.object(Report, "get_data", return_value=([], [])) as get_data:
			self.run_scheduler_job(name)

		get_data.assert_called_once()

	def test_approval_is_not_open_to_the_generic_ai_write_tools(self):
		self.assertIn(APPROVAL, frappe.get_hooks("ai_write_closed_doctypes") or [])
		self.assertRaises(
			frappe.ValidationError,
			frappe.get_doc(
				{
					"doctype": "Access Rule",
					"title": "x",
					"document_type": APPROVAL,
					"role": "ER IK",
					"scope": "all",
					"allow_read": 1,
				}
			).insert,
		)


class TestSwitchOffOnMigrate(AutoEmailReportTestCase):
	def enabled(self, name: str) -> int:
		return frappe.db.get_value(RECORD, name, "enabled")

	def test_install_and_migrate_hooks_are_registered(self):
		path = "platform_core.erisim.reports.switch_off_unapproved_auto_email_reports"

		self.assertIn(path, frappe.get_hooks("after_migrate"))
		self.assertIn(path, frappe.get_hooks("after_install"))

	def test_unapproved_governed_records_are_switched_off(self):
		governed = self.legacy(BUILDER_REPORT)
		query = self.legacy(NAME_REPORT, report_type="Query Report")
		free = self.legacy(FREE_BUILDER_REPORT)
		approved = self.approved(BUILDER_REPORT, EMPLOYEE_1)

		reports.switch_off_unapproved_auto_email_reports()

		self.assertEqual((self.enabled(governed), self.enabled(query)), (0, 0))
		self.assertEqual((self.enabled(free), self.enabled(approved)), (1, 1))

	def test_switched_off_record_comes_back_only_by_a_system_manager_saving_it(self):
		name = self.legacy(BUILDER_REPORT)
		reports.switch_off_unapproved_auto_email_reports()
		frappe.db.commit()  # nosemgrep: the request uses another connection

		frappe.set_user(HR)
		doc = frappe.get_doc(RECORD, name)
		doc.enabled = 1
		self.assertRaises(frappe.PermissionError, doc.save)

		frappe.set_user(ADMIN)
		doc = frappe.get_doc(RECORD, name)
		doc.enabled = 1
		doc.save()
		frappe.set_user("Administrator")

		self.assertEqual(self.enabled(name), 1)
		self.assertEqual(frappe.db.get_value(APPROVAL, name, "approved_by"), ADMIN)


class TestContentAndSession(AutoEmailReportTestCase):
	def test_list_report_content_is_limited_to_the_record_user(self):
		"""Frappe reads a list report with the record's user. Only that user's records are in it."""
		frappe.db.set_value(DOCTYPE, self.records[EMPLOYEE_1], "salary_amount", SALARY)
		name = self.approved(BUILDER_REPORT, EMPLOYEE_1, no_of_rows=500)
		frappe.set_user(ADMIN)

		content = frappe.get_doc(RECORD, name).get_report_content()

		text = content.decode() if isinstance(content, bytes) else str(content)
		self.assertIn(self.records[EMPLOYEE_1], text)
		for owner, record in self.records.items():
			if owner != EMPLOYEE_1:
				self.assertNotIn(record, text)
		self.assertNotIn(str(SALARY), text)

	def test_engine_never_switches_the_session_user(self):
		"""`frappe.set_user` resets the session. The engine must not call it."""
		name = self.approved(BUILDER_REPORT, EMPLOYEE_1)
		frappe.set_user(ADMIN)
		frappe.session.data["marker"] = "kept"
		session_id = frappe.session.sid
		doc = frappe.get_doc(RECORD, name)

		with patch.object(frappe, "set_user") as set_user:
			doc.get_report_content()

		set_user.assert_not_called()
		self.assertEqual((frappe.session.user, frappe.session.sid), (ADMIN, session_id))
		self.assertEqual(frappe.session.data.get("marker"), "kept")


class TestWithoutRules(AutoEmailReportTestCase):
	"""Without governed data the engine leaves Auto Email Report to Frappe."""

	RULES = ()

	def test_report_manager_is_not_refused_and_nothing_is_switched_off(self):
		name = self.legacy(BUILDER_REPORT, HR)

		reports.switch_off_unapproved_auto_email_reports()

		self.assertEqual(frappe.db.get_value(RECORD, name, "enabled"), 1)
		self.assertFalse(self.gate_refuses(self.auto_report(BUILDER_REPORT, HR), HR))
