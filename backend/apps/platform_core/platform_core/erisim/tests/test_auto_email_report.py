"""Auto Email Report on governed data is switched off for everyone.

The record runs a report later, without a user being present, and mails the result. The
project runs no scheduled jobs (D-6) and the first release needs no email reports. An approval
scheme was tried and every review found a new way around it, so the rule is the simplest one:

- A record that touches governed data cannot be created, cannot be enabled, cannot be
  downloaded and cannot be sent, by hand or by the scheduler. This holds for every user,
  System Manager and Administrator included.
- Installing and migrating switch off every such record that is still enabled.
- A record on data that is not governed is left to Frappe.
"""

from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.core.doctype.report.report import Report
from frappe.email.doctype.auto_email_report import auto_email_report
from frappe.utils.background_jobs import execute_job

import platform_core
from platform_core.erisim import reports
from platform_core.erisim.tests.base import ADMIN, EMPLOYEE_1, HR, ErisimTestCase
from platform_core.erisim.tests.test_report_rules import (
	BUILDER_REPORT,
	FREE_BUILDER_REPORT,
	NAME_REPORT,
	SCRIPT_REPORT,
	ensure_reports,
)

RECORD = "Auto Email Report"
REPORT_MANAGER = "Report Manager"
SCHEDULER_JOB = "frappe.email.doctype.auto_email_report.auto_email_report.process_auto_email_report"
EVERYONE = (EMPLOYEE_1, HR, ADMIN, "Administrator")
GOVERNED_REPORTS = (
	(NAME_REPORT, "Query Report"),
	(SCRIPT_REPORT, "Script Report"),
	(BUILDER_REPORT, "Report Builder"),
)


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
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		if hasattr(frappe.local, "job"):
			del frappe.local.job
		frappe.get_doc("User", HR).remove_roles(REPORT_MANAGER)
		frappe.db.delete(RECORD)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def auto_report(self, report: str, user: str = ADMIN, report_type: str = "Report Builder", **values):
		return frappe.get_doc(
			{
				"doctype": RECORD,
				"report": report,
				"report_type": report_type,
				"user": user,
				"enabled": 1,
				"email_to": "ar.reader@example.test",
				"format": "CSV",
				"frequency": "Daily",
				**values,
			}
		)

	def legacy(self, report: str, report_type: str = "Report Builder", **values) -> str:
		"""A record saved before the rule existed: written without any check."""
		doc = self.auto_report(report, ADMIN, report_type, **values)
		doc.name = f"{report} legacy"
		doc.db_insert()
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		return doc.name

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

	def assert_not_run(self, name: str) -> None:
		"""The scheduler job ends without running the report and without queueing an email."""
		before = frappe.db.count("Email Queue")
		with patch.object(Report, "get_data") as get_data, patch.object(frappe, "sendmail") as sendmail:
			self.run_scheduler_job(name)
		get_data.assert_not_called()
		sendmail.assert_not_called()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Email Queue"), before)


class TestSwitchedOffForEveryone(AutoEmailReportTestCase):
	def test_nobody_can_create_one(self):
		for report, report_type in GOVERNED_REPORTS:
			for caller in EVERYONE:
				with self.subTest(report=report, caller=caller):
					self.assertTrue(self.gate_refuses(self.auto_report(report, ADMIN, report_type), caller))
					self.assertTrue(
						self.gate_refuses(self.auto_report(report, ADMIN, report_type, enabled=0), caller)
					)
		frappe.set_user(ADMIN)
		self.assertRaises(frappe.PermissionError, self.auto_report(BUILDER_REPORT).insert)
		frappe.set_user("Administrator")
		self.assertRaises(frappe.PermissionError, self.auto_report(BUILDER_REPORT).insert)
		self.assertFalse(frappe.db.count(RECORD))

	def test_nobody_can_create_one_over_the_rest_apis(self):
		client = self.login(ADMIN)
		body = self.auto_report(BUILDER_REPORT).as_dict(no_default_fields=True)

		version_1 = self.send(client, "POST", f"/api/resource/{RECORD}", body=body)
		version_2 = self.send(client, "POST", f"/api/v2/document/{RECORD}", body=body)

		for response in (version_1, version_2):
			self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertFalse(frappe.db.count(RECORD))

	def test_nobody_can_enable_an_existing_one(self):
		name = self.legacy(BUILDER_REPORT, enabled=0)

		for caller in (HR, ADMIN, "Administrator"):
			with self.subTest(caller=caller):
				frappe.set_user(caller)
				doc = frappe.get_doc(RECORD, name)
				doc.enabled = 1
				self.assertRaises(frappe.PermissionError, doc.save)
				frappe.set_user("Administrator")
		client = self.login(ADMIN)
		for path in (f"/api/resource/{RECORD}/{name}", f"/api/v2/document/{RECORD}/{name}"):
			response = self.send(client, "PUT", path, body={"enabled": 1})
			self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertEqual(frappe.db.get_value(RECORD, name, "enabled"), 0)

	def test_existing_one_can_still_be_switched_off_or_deleted(self):
		"""The rule must not trap a record in the enabled state."""
		name = self.legacy(BUILDER_REPORT)
		frappe.set_user(ADMIN)
		doc = frappe.get_doc(RECORD, name)
		doc.enabled = 0

		doc.save()

		self.assertEqual(frappe.db.get_value(RECORD, name, "enabled"), 0)
		frappe.delete_doc(RECORD, name)
		self.assertFalse(frappe.db.exists(RECORD, name))

	def test_nobody_can_download_or_send_an_existing_one(self):
		for report, report_type in GOVERNED_REPORTS:
			name = self.legacy(report, report_type)
			for caller in (HR, ADMIN, "Administrator"):
				with self.subTest(report=report, caller=caller):
					frappe.set_user(caller)
					doc = frappe.get_doc(RECORD, name)
					with (
						patch.object(Report, "get_data") as get_data,
						patch.object(frappe, "sendmail") as sendmail,
					):
						self.assertRaises(frappe.PermissionError, auto_email_report.download, name)
						self.assertRaises(frappe.PermissionError, auto_email_report.send_now, name)
						self.assertRaises(frappe.PermissionError, doc.send)
						self.assertRaises(frappe.PermissionError, doc.get_report_content)
					get_data.assert_not_called()
					sendmail.assert_not_called()
					frappe.set_user("Administrator")

	def test_scheduler_does_not_run_an_existing_one(self):
		"""The scheduler works as Administrator. That session opens nothing here."""
		for report, report_type in GOVERNED_REPORTS:
			with self.subTest(report=report):
				self.assert_not_run(self.legacy(report, report_type))

	def test_monthly_scheduler_path_does_not_run_it_either(self):
		name = self.legacy(BUILDER_REPORT, frequency="Monthly")
		before = frappe.db.count("Email Queue")

		with patch.object(Report, "get_data") as get_data, patch.object(frappe, "sendmail") as sendmail:
			try:
				auto_email_report.send_monthly()
			except frappe.PermissionError:
				pass

		get_data.assert_not_called()
		sendmail.assert_not_called()
		self.assertEqual(frappe.db.count("Email Queue"), before)
		self.assertTrue(frappe.db.exists(RECORD, name))


class TestNoApprovalScheme(AutoEmailReportTestCase):
	"""The approval record, its fingerprint and its code are gone."""

	def test_engine_has_no_approval_code(self):
		for name in (
			"APPROVAL",
			"record_approval",
			"approval_is_valid",
			"settings_digest",
			"is_system_manager",
		):
			self.assertFalse(hasattr(reports, name), name)
		folder = Path(platform_core.__file__).parent / "erisim" / "doctype" / "auto_email_report_approval"
		self.assertFalse(folder.exists())

	def test_no_hook_names_the_approval_document_type(self):
		self.assertNotIn("Auto Email Report Approval", frappe.get_hooks("ai_write_closed_doctypes") or [])

	def test_saving_by_a_system_manager_opens_nothing(self):
		"""Saving was the approval once. It is not any more."""
		name = self.legacy(BUILDER_REPORT, enabled=0)
		frappe.set_user(ADMIN)
		frappe.get_doc(RECORD, name).save()

		self.assertRaises(frappe.PermissionError, auto_email_report.download, name)
		frappe.set_user("Administrator")
		self.assert_not_run(name)


class TestSwitchOffOnInstallAndMigrate(AutoEmailReportTestCase):
	def enabled(self, name: str) -> int:
		return frappe.db.get_value(RECORD, name, "enabled")

	def test_install_and_migrate_hooks_are_registered(self):
		path = "platform_core.erisim.reports.switch_off_governed_auto_email_reports"

		self.assertIn(path, frappe.get_hooks("after_migrate"))
		self.assertIn(path, frappe.get_hooks("after_install"))

	def test_every_enabled_record_on_governed_data_is_switched_off(self):
		governed = [self.legacy(report, report_type) for report, report_type in GOVERNED_REPORTS]
		free = self.legacy(FREE_BUILDER_REPORT)

		with self.assertLogs("platform_core.erisim", level="INFO") as logged:
			reports.switch_off_governed_auto_email_reports()

		self.assertEqual([self.enabled(name) for name in governed], [0, 0, 0])
		self.assertEqual(self.enabled(free), 1)
		# The log says how many were switched off. A record name comes from the report title
		# (`frappe/email/doctype/auto_email_report/auto_email_report.py:70`) and a title can hold
		# the name of a person, so no name is logged.
		text = "\n".join(logged.output)
		self.assertIn("3", text)
		for name in (*governed, free):
			self.assertNotIn(name, text)
		for report, _report_type in GOVERNED_REPORTS:
			self.assertNotIn(report, text)


class TestUngovernedData(AutoEmailReportTestCase):
	def test_report_manager_creates_and_runs_one(self):
		frappe.set_user(HR)
		name = self.auto_report(FREE_BUILDER_REPORT, HR).insert().name
		frappe.set_user("Administrator")
		# Committed on purpose: the job reads committed data.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

		with patch.object(Report, "get_data", return_value=([], [])) as get_data:
			self.run_scheduler_job(name)

		get_data.assert_called_once()

	def test_engine_never_switches_the_session_user(self):
		"""`frappe.set_user` resets the session. The engine must not call it."""
		name = self.legacy(FREE_BUILDER_REPORT)
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

	def test_nothing_is_refused_and_nothing_is_switched_off(self):
		name = self.legacy(BUILDER_REPORT)

		reports.switch_off_governed_auto_email_reports()

		self.assertEqual(frappe.db.get_value(RECORD, name, "enabled"), 1)
		self.assertFalse(self.gate_refuses(self.auto_report(BUILDER_REPORT, HR), HR))
