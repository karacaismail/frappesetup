"""Report rules on governed data.

A. Prepared Report is closed for a report that touches governed data: creating one, reading a
   stored result, downloading its file alone or in a ZIP, and converting it to CSV.
B. A query report runs only for a System Manager while any document type is governed. What its
   SQL reads cannot be verified.
C. A script report follows the same rule. Its code cannot be verified either: a static check
   was tried and two reviews found ways around it (an aliased import, a `user` argument).
   There is no declaration and no code check any more.
E. Auto Email Report follows the same rules for the user it runs as, and runs as that user.
"""

import inspect
import json
from unittest.mock import patch

import frappe
import frappe.share
from frappe.core.doctype.prepared_report import prepared_report
from frappe.core.doctype.report.report import Report
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

# Code that looks permission-aware. Each one is a way around the static check that was removed.
SAFE_LOOKING_SCRIPT = (
	f'rows = frappe.get_list("{DOCTYPE}", fields=["name", "title"])\nresult = [[row.name] for row in rows]\n'
)
ALIASED_SCRIPT = f'import frappe as f\nresult = f.get_all("{DOCTYPE}", fields=["name"], as_list=True)\n'
REASSIGNED_SCRIPT = f'f = frappe\nresult = f.get_all("{DOCTYPE}", fields=["name"], as_list=True)\n'
OTHER_USER_SCRIPT = (
	f'result = frappe.get_list("{DOCTYPE}", fields=["name"], user="Administrator", as_list=True)\n'
)
POSITIONAL_SCRIPT = (
	f'result = frappe.get_list("{DOCTYPE}", ["name"], None, None, None, None, None, None, True)\n'
)
SCOPE = {DOCTYPE: ["name", "title"]}


def with_scope_declaration(report: str):
	"""Pretend an app declared a scope for the report through the removed hooks."""
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		if hook == "access_rule_report_scopes":
			return {report: [SCOPE]}
		if hook == "access_rule_aware_reports":
			return [report]
		return original(hook, *args, **kwargs)

	return patch.object(frappe, "get_hooks", get_hooks)


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
	ensure_report(SCRIPT_REPORT, DOCTYPE, "Script Report", report_script=SAFE_LOOKING_SCRIPT)
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
		with with_scope_declaration(NAME_REPORT):
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

	def test_guard_signatures_other_modules_rely_on_are_stable(self):
		"""The AI layer calls the guard as `guard(report_name)` and may pass a user."""
		for function in (api.report_guard, reports.guard):
			parameters = list(inspect.signature(function).parameters.values())
			self.assertEqual([parameter.name for parameter in parameters], ["report_name", "user"])
			self.assertIsNone(parameters[1].default)


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
	"""Decision C: a script report on a site with governed data runs for a System Manager only."""

	def set_script(self, script: str) -> None:
		frappe.set_user("Administrator")
		frappe.db.set_value("Report", SCRIPT_REPORT, "report_script", script)
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def setUp(self):
		super().setUp()
		self.addCleanup(self.set_script, SAFE_LOOKING_SCRIPT)

	def test_script_report_is_refused_for_everyone_but_a_system_manager(self):
		for user in (EMPLOYEE_1, MANAGER_1, HR, NO_RULE):
			with self.subTest(user=user):
				self.assertTrue(self.denied(SCRIPT_REPORT, user))
				self.assert_refused(self.run_report(self.login(user), SCRIPT_REPORT))
		self.assertFalse(self.denied(SCRIPT_REPORT, ADMIN))

	def test_code_that_looks_permission_aware_is_refused_without_reading_data(self):
		"""Each script got past the static check that was removed. None of them runs now."""
		scripts = (
			SAFE_LOOKING_SCRIPT,
			ALIASED_SCRIPT,
			REASSIGNED_SCRIPT,
			OTHER_USER_SCRIPT,
			POSITIONAL_SCRIPT,
		)
		for script in scripts:
			self.set_script(script)
			for user in (EMPLOYEE_1, HR):
				with self.subTest(script=script.splitlines()[0], user=user):
					frappe.set_user(user)
					with patch.object(Report, "execute_script") as execute:
						self.assertRaises(frappe.PermissionError, query_report.run, SCRIPT_REPORT, {})
						self.assertRaises(
							frappe.PermissionError, frappe.get_doc("Report", SCRIPT_REPORT).get_data
						)
					execute.assert_not_called()
					frappe.set_user("Administrator")
					self.assert_refused(self.run_report(self.login(user), SCRIPT_REPORT))

	def test_app_declaration_does_not_open_a_script_report(self):
		"""The `access_rule_report_scopes` hook is gone. Declaring a scope changes nothing."""
		client = self.login(HR)
		with with_scope_declaration(SCRIPT_REPORT):
			self.assertTrue(self.denied(SCRIPT_REPORT, EMPLOYEE_1))
			self.assertTrue(self.denied(SCRIPT_REPORT, HR))
			response = self.run_report(client, SCRIPT_REPORT)

		self.assert_refused(response)

	def test_engine_offers_no_declaration_or_code_check(self):
		for name in ("declared_scope", "declared_hook", "script_report_problem", "SCOPES_HOOK"):
			self.assertFalse(hasattr(reports, name), name)
		self.assertRaises(ImportError, frappe.get_module, "platform_core.erisim.code_check")

	def test_script_report_is_closed_for_prepared_reports_too(self):
		self.assertTrue(reports.touches_governed(SCRIPT_REPORT))


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

	def auto_report(self, report: str, user: str, report_type: str = "Query Report", **values):
		return frappe.get_doc(
			doctype="Auto Email Report",
			report=report,
			report_type=report_type,
			user=user,
			enabled=1,
			email_to="ar.reader@example.test",
			format="CSV",
			frequency="Daily",
			**values,
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

	def test_query_and_script_reports_need_a_system_manager_as_the_record_user(self):
		for report, report_type in ((NAME_REPORT, "Query Report"), (SCRIPT_REPORT, "Script Report")):
			for user in (EMPLOYEE_1, MANAGER_1, HR):
				with self.subTest(report=report, user=user):
					self.assertTrue(self.gate_refuses(self.auto_report(report, user, report_type)))
			self.assertFalse(self.gate_refuses(self.auto_report(report, ADMIN, report_type)))

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

	def test_report_content_holds_only_what_the_record_user_may_see(self):
		"""An administrator downloads a report made for an employee. Only the employee's record is in it."""
		frappe.db.set_value(DOCTYPE, self.records[EMPLOYEE_1], "salary_amount", SALARY)
		doc = self.auto_report(BUILDER_REPORT, EMPLOYEE_1, "Report Builder", no_of_rows=500)
		frappe.set_user(ADMIN)

		content = doc.get_report_content()

		text = content.decode() if isinstance(content, bytes) else str(content)
		self.assertIn(self.records[EMPLOYEE_1], text)
		for owner, name in self.records.items():
			if owner != EMPLOYEE_1:
				self.assertNotIn(name, text)
		self.assertNotIn(str(SALARY), text)

	def test_report_runs_as_the_record_user_and_the_session_user_comes_back(self):
		seen = []

		def record_user(*args, **kwargs):
			seen.append(frappe.session.user)
			return [], []

		doc = self.auto_report(BUILDER_REPORT, EMPLOYEE_1, "Report Builder")
		frappe.set_user(ADMIN)

		with patch.object(Report, "get_data", record_user):
			doc.get_report_content()

		self.assertEqual(seen, [EMPLOYEE_1])
		self.assertEqual(frappe.session.user, ADMIN)

	def test_session_user_comes_back_when_the_report_fails(self):
		def fail(*args, **kwargs):
			raise RuntimeError("report failed")

		doc = self.auto_report(BUILDER_REPORT, EMPLOYEE_1, "Report Builder")
		frappe.set_user(ADMIN)

		with patch.object(Report, "get_data", fail):
			self.assertRaises(RuntimeError, doc.get_report_content)

		self.assertEqual(frappe.session.user, ADMIN)
