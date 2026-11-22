"""Report rules on governed data (third review, orchestrator decisions A, B, C and E).

A. Prepared Report is closed for a report that touches governed data: creating one, reading a
   stored result, downloading its file alone or in a ZIP, and converting it to CSV.
B. A query report runs only for a System Manager while any document type is governed. What its
   SQL reads cannot be verified.
C. A script report runs only when an app declared what it reads and its code reads through
   permission-aware calls. The check runs on every execution.
E. Auto Email Report follows the same rules for the user it runs as.
"""

import json
from unittest.mock import patch

import frappe
import frappe.share
from frappe.core.doctype.prepared_report import prepared_report
from frappe.desk import query_report
from frappe.email.doctype.auto_email_report import auto_email_report

from platform_core.erisim import api, reports
from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	FREE_DOCTYPE,
	HR,
	MANAGER_1,
	NO_RULE,
	ROLE_MANAGER,
	RULE_DOCTYPE,
	ErisimTestCase,
)

RUN = "/api/method/frappe.desk.query_report.run"
EXPORT = "/api/method/frappe.desk.query_report.export_query"
PREPARED = "/api/method/frappe.core.doctype.prepared_report.prepared_report."
ZIP = "/api/method/frappe.core.api.file.zip_files"
NAME_REPORT = "AR Test Name Report"
CROSS_REPORT = "AR Test Cross Type Report"
SALARY_REPORT = "AR Test Salary Report"
FREE_REPORT = "AR Test Free Report"
BUILDER_REPORT = "AR Test Builder Report"
SCRIPT_REPORT = "AR Test Script Report"
SALARY = 987652

SAFE_SCRIPT = (
	f'rows = frappe.get_list("{DOCTYPE}", fields=["name", "title"])\nresult = [[row.name] for row in rows]\n'
)
UNSAFE_SCRIPT = f'result = frappe.db.sql("select name from `tab{DOCTYPE}`")\n'
OTHER_TYPE_SCRIPT = f'result = frappe.get_list("{RULE_DOCTYPE}", fields=["name"])\n'
SCOPE = {DOCTYPE: ["name", "title"]}


def ensure_report(name: str, ref_doctype: str, report_type: str = "Query Report", **values) -> None:
	if not frappe.db.exists("Report", name):
		frappe.get_doc(
			doctype="Report",
			report_name=name,
			ref_doctype=ref_doctype,
			report_type=report_type,
			is_standard="No",
			**values,
		).insert()


def ensure_reports() -> None:
	columns = "name as `Name:Data:200`, title as `Title:Data:200`"
	ensure_report(NAME_REPORT, DOCTYPE, query=f"select {columns} from `tab{DOCTYPE}`")
	# The report belongs to an ungoverned type but reads the governed one.
	ensure_report(CROSS_REPORT, FREE_DOCTYPE, query=f"select {columns} from `tab{DOCTYPE}`")
	ensure_report(
		SALARY_REPORT,
		DOCTYPE,
		query=f"select name as `Name:Data:200`, salary_amount as `Salary:Currency:120` from `tab{DOCTYPE}`",
	)
	ensure_report(FREE_REPORT, FREE_DOCTYPE, query=f"select {columns} from `tab{FREE_DOCTYPE}`")
	ensure_report(BUILDER_REPORT, DOCTYPE, "Report Builder")
	ensure_report(SCRIPT_REPORT, DOCTYPE, "Script Report", report_script=SAFE_SCRIPT)
	frappe.db.commit()  # nosemgrep: the request uses another connection


class ReportRulesTestCase(ErisimTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_reports()

	def run_report(self, client, report: str, **extra):
		return self.send(client, "POST", RUN, body={"report_name": report, "filters": "{}", **extra})

	def assert_refused(self, response, statuses=(403,)) -> None:
		self.assertIn(response.status_code, statuses, response.get_data(as_text=True)[:300])
		body = response.get_data(as_text=True)
		for name in self.records.values():
			self.assertNotIn(name, body)

	def denied(self, report: str, user: str) -> bool:
		frappe.set_user(user)
		try:
			return bool(reports.denial(report))
		finally:
			frappe.set_user("Administrator")


class TestQueryReportRule(ReportRulesTestCase):
	"""Decision B."""

	def test_only_a_system_manager_runs_a_query_report(self):
		for report in (NAME_REPORT, CROSS_REPORT):
			for user in (EMPLOYEE_1, MANAGER_1, HR, NO_RULE):
				with self.subTest(report=report, user=user):
					self.assert_refused(self.run_report(self.login(user), report))
			with self.subTest(report=report, user=ADMIN):
				response = self.run_report(self.login(ADMIN), report)
				self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
				self.assertIn(self.records[EMPLOYEE_1], response.get_data(as_text=True))

	def test_report_of_an_ungoverned_type_is_closed_too_while_rules_exist(self):
		"""The SQL may read any table, so the report's own document type proves nothing."""
		self.assert_refused(self.run_report(self.login(NO_RULE), FREE_REPORT))

	def test_declaration_does_not_open_a_query_report(self):
		with patch.object(reports, "declared_scope", return_value=SCOPE):
			response = self.run_report(self.login(HR), NAME_REPORT)

		self.assert_refused(response)

	def test_export_is_refused(self):
		body = {"report_name": NAME_REPORT, "file_format_type": "CSV", "filters": "{}"}

		self.assert_refused(self.send(self.login(HR), "POST", EXPORT, body=body))

	def test_python_caller_is_refused_without_any_endpoint(self):
		frappe.set_user(HR)

		self.assertRaises(frappe.PermissionError, query_report.run, NAME_REPORT, {})
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Report", NAME_REPORT).get_data)

	def test_background_export_job_checks_again_when_it_runs(self):
		"""The System Manager role is removed after the export was queued."""
		form = frappe._dict(report_name=NAME_REPORT, file_format_type="CSV", filters="{}")
		frappe.get_doc("User", ADMIN).remove_roles("System Manager")
		self.addCleanup(lambda: frappe.get_doc("User", ADMIN).add_roles("System Manager"))
		frappe.set_user(ADMIN)

		self.assertRaises(
			frappe.PermissionError, query_report.run_export_query_job, "ar.reader@example.test", form, {}
		)

	def test_public_guard_gives_the_same_answer(self):
		"""Other modules call the gate through `platform_core.erisim.api`."""
		frappe.set_user(EMPLOYEE_1)
		self.assertRaises(frappe.PermissionError, api.report_guard, NAME_REPORT)
		frappe.set_user("Administrator")
		self.assertRaises(frappe.PermissionError, api.report_guard, NAME_REPORT, HR)
		self.assertIsNone(api.report_guard(NAME_REPORT, ADMIN))


class TestReportsWithoutRules(ReportRulesTestCase):
	"""With no governed document type the gate only keeps the field level of the report's own type."""

	RULES = ()

	def test_query_report_runs_for_a_user_with_role_permission(self):
		response = self.run_report(self.login(HR), NAME_REPORT)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])

	def test_restricted_field_still_needs_its_level(self):
		frappe.db.set_value(DOCTYPE, self.records[EMPLOYEE_1], "salary_amount", SALARY)
		frappe.db.commit()  # nosemgrep: the request uses another connection

		refused = self.run_report(self.login(MANAGER_1), SALARY_REPORT)
		allowed = self.run_report(self.login(HR), SALARY_REPORT)

		self.assertEqual(refused.status_code, 403, refused.get_data(as_text=True)[:300])
		self.assertNotIn(str(SALARY), refused.get_data(as_text=True))
		self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True)[:300])
		self.assertIn(str(SALARY), allowed.get_data(as_text=True))

	def test_prepared_report_stays_open(self):
		self.assertFalse(reports.touches_governed(NAME_REPORT))


class TestScriptReportRule(ReportRulesTestCase):
	"""Decision C."""

	def set_script(self, script: str) -> None:
		frappe.db.set_value("Report", SCRIPT_REPORT, "report_script", script)

	def setUp(self):
		super().setUp()
		self.addCleanup(self.set_script, SAFE_SCRIPT)

	def test_undeclared_script_report_does_not_run(self):
		for user in (EMPLOYEE_1, HR, ADMIN):
			with self.subTest(user=user):
				self.assertTrue(self.denied(SCRIPT_REPORT, user))
		self.assert_refused(self.run_report(self.login(HR), SCRIPT_REPORT))

	def test_empty_or_incomplete_declaration_does_not_run(self):
		for scope in ({}, {DOCTYPE: []}, {DOCTYPE: None}, {"AR No Such Type": ["name"]}, {DOCTYPE: ["*"]}):
			with self.subTest(scope=scope), patch.object(reports, "declared_hook", return_value=scope):
				self.assertTrue(self.denied(SCRIPT_REPORT, HR))

	def test_declared_report_with_permission_aware_code_runs(self):
		with patch.object(reports, "declared_hook", return_value=SCOPE):
			self.assertFalse(self.denied(SCRIPT_REPORT, EMPLOYEE_1))
			self.assertFalse(self.denied(SCRIPT_REPORT, HR))

	def test_declared_report_with_raw_reads_does_not_run(self):
		self.set_script(UNSAFE_SCRIPT)

		with patch.object(reports, "declared_hook", return_value=SCOPE):
			self.assertTrue(self.denied(SCRIPT_REPORT, HR))
			self.assertTrue(self.denied(SCRIPT_REPORT, ADMIN))

	def test_reading_a_type_outside_the_declaration_does_not_run(self):
		self.set_script(OTHER_TYPE_SCRIPT)

		with patch.object(reports, "declared_hook", return_value=SCOPE):
			self.assertTrue(self.denied(SCRIPT_REPORT, ADMIN))

	def test_user_needs_role_permission_on_every_declared_type(self):
		scope = {**SCOPE, RULE_DOCTYPE: ["name"]}

		with patch.object(reports, "declared_hook", return_value=scope):
			self.assertTrue(self.denied(SCRIPT_REPORT, EMPLOYEE_1))
			self.assertFalse(self.denied(SCRIPT_REPORT, ADMIN))

	def test_scope_is_verified_again_after_the_report_changes(self):
		with patch.object(reports, "declared_hook", return_value=SCOPE):
			self.assertFalse(self.denied(SCRIPT_REPORT, HR))
			self.set_script(UNSAFE_SCRIPT)
			self.assertTrue(self.denied(SCRIPT_REPORT, HR))

	def test_self_declared_aware_list_no_longer_exists(self):
		"""A report cannot switch the scope check off by naming itself."""
		self.assertFalse(hasattr(reports, "AWARE_REPORTS_HOOK"))
		with patch.object(frappe, "get_hooks", return_value=[SCRIPT_REPORT, NAME_REPORT]):
			self.assertIsNone(reports.declared_scope(SCRIPT_REPORT))


class TestPreparedReportClosed(ReportRulesTestCase):
	"""Decision A."""

	def setUp(self):
		super().setUp()
		self.addCleanup(self.cleanup)
		self.prepared, self.file, self.file_url = self.existing_result()

	def existing_result(self):
		"""Stand-in for a result that was stored before the document type became governed."""
		doc = frappe.get_doc(doctype="Prepared Report", report_name=NAME_REPORT, status="Completed")
		doc.name = frappe.generate_hash(length=10)
		doc.owner = ADMIN
		doc.db_insert()
		rows = [{"name": name, "title": "stored"} for name in self.records.values()]
		with patch.object(reports, "touches_governed", return_value=False):
			prepared_report.create_json_gz_file({"result": rows}, "Prepared Report", doc.name, NAME_REPORT)
		file = frappe.db.get_value(
			"File",
			{"attached_to_doctype": "Prepared Report", "attached_to_name": doc.name},
			["name", "file_url"],
			as_dict=True,
		)
		frappe.db.set_value("File", file.name, "owner", ADMIN)
		frappe.db.commit()  # nosemgrep: the request uses another connection
		return doc.name, file.name, file.file_url

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("DocShare", {"share_doctype": "File"})
		frappe.db.delete("File", {"attached_to_doctype": "Prepared Report"})
		frappe.db.delete("Prepared Report", {"report_name": NAME_REPORT})
		frappe.db.commit()  # nosemgrep

	def test_cannot_be_created_by_anyone(self):
		for user in (EMPLOYEE_1, HR, ADMIN, "Administrator"):
			with self.subTest(user=user):
				frappe.set_user(user)
				doc = frappe.get_doc({"doctype": "Prepared Report", "report_name": NAME_REPORT})
				self.assertRaises(frappe.PermissionError, doc.insert, ignore_permissions=True)
				frappe.set_user("Administrator")

	def test_endpoint_does_not_queue_one(self):
		before = frappe.db.count("Prepared Report")

		response = self.send(
			self.login(ADMIN), "POST", PREPARED + "make_prepared_report", body={"report_name": NAME_REPORT}
		)

		self.assert_refused(response)
		self.assertEqual(frappe.db.count("Prepared Report"), before)

	def test_stored_result_cannot_be_downloaded(self):
		response = self.send(
			self.login(ADMIN), "GET", PREPARED + "download_attachment", query={"dn": self.prepared}
		)

		# Frappe reports this refusal as a validation error (417), not as 403.
		self.assert_refused(response, (403, 417))

	def test_stored_result_cannot_be_read_through_run(self):
		response = self.run_report(self.login(ADMIN), NAME_REPORT, prepared_report_name=self.prepared)

		self.assertNotIn("stored", response.get_data(as_text=True))

	def test_stored_file_cannot_be_read_by_its_owner_or_through_a_share(self):
		frappe.share.add_docshare("File", self.file, EMPLOYEE_1, read=1)
		frappe.db.commit()  # nosemgrep: the request uses another connection

		for user in (ADMIN, EMPLOYEE_1):
			with self.subTest(user=user):
				self.assertEqual(self.send(self.login(user), "GET", self.file_url).status_code, 403)

	def test_stored_file_cannot_be_downloaded_in_a_zip(self):
		response = self.send(self.login(ADMIN), "POST", ZIP, body={"files": json.dumps([self.file])})

		self.assertNotEqual(response.status_code, 200)

	def test_stored_result_cannot_be_converted_to_csv(self):
		frappe.set_user(ADMIN)

		self.assertRaises(
			frappe.PermissionError, prepared_report.enqueue_json_to_csv_conversion, self.prepared
		)

	def test_stored_content_is_closed_for_code_too(self):
		"""Even code running as Administrator cannot read the stored content."""
		doc = frappe.get_doc("Prepared Report", self.prepared)

		self.assertRaises(frappe.PermissionError, doc.get_prepared_data)
		self.assertRaises(frappe.PermissionError, frappe.get_doc("File", self.file).get_content)


class TestAutoEmailReportRules(ReportRulesTestCase):
	"""Decision E."""

	RULES = (
		*ErisimTestCase.RULES,
		{"title": "Manager all records", "role": ROLE_MANAGER, "scope": "all", "allow_read": 1},
	)

	def auto_report(self, report: str, user: str, report_type: str = "Query Report"):
		return frappe.get_doc(
			doctype="Auto Email Report",
			report=report,
			report_type=report_type,
			user=user,
			enabled=1,
			email_to="ar.reader@example.test",
			format="CSV",
			frequency="Daily",
		)

	def gate_refuses(self, doc) -> bool:
		"""Only the gate's refusal counts. Frappe's own validation of the record is not under test."""
		try:
			doc.validate()
		except frappe.PermissionError:
			return True
		except frappe.ValidationError:
			return False
		return False

	def test_query_report_follows_rule_b_for_the_record_user(self):
		for user in (EMPLOYEE_1, MANAGER_1, HR):
			with self.subTest(user=user):
				self.assertTrue(self.gate_refuses(self.auto_report(NAME_REPORT, user)))
		self.assertFalse(self.gate_refuses(self.auto_report(NAME_REPORT, ADMIN)))

	def test_script_report_follows_rule_c(self):
		self.assertTrue(self.gate_refuses(self.auto_report(SCRIPT_REPORT, ADMIN, "Script Report")))
		with patch.object(reports, "declared_hook", return_value=SCOPE):
			self.assertFalse(self.gate_refuses(self.auto_report(SCRIPT_REPORT, EMPLOYEE_1, "Script Report")))

	def test_saved_record_cannot_be_inserted_for_a_refused_user(self):
		self.assertRaises(frappe.PermissionError, self.auto_report(NAME_REPORT, HR).insert)
		self.assertFalse(frappe.db.count("Auto Email Report"))

	def test_existing_record_is_refused_when_it_runs(self):
		"""The record was saved earlier. The rule is applied again each time it runs."""
		doc = self.auto_report(NAME_REPORT, HR)
		doc.name = NAME_REPORT
		doc.db_insert()
		self.addCleanup(frappe.db.delete, "Auto Email Report", {"name": doc.name})

		self.assertRaises(frappe.PermissionError, auto_email_report.download, doc.name)
		self.assertRaises(frappe.PermissionError, auto_email_report.send_now, doc.name)
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Auto Email Report", doc.name).send)
