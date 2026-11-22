"""Report rules on governed data.

A. Prepared Report is closed for a report that touches governed data: creating one, reading a
   stored result, downloading its file alone or in a ZIP, and converting it to CSV.
B. A query report runs only for a System Manager while any document type is governed. What its
   SQL reads cannot be verified.
C. A script report follows the same rule. Its code cannot be verified either: a static check
   was tried and two reviews found ways around it (an aliased import, a `user` argument).
   There is no declaration and no code check any more.
E. Auto Email Report has its own tests in `test_auto_email_report.py`.
"""

import inspect
import json
from unittest.mock import patch

import frappe
import frappe.share
from frappe.core.doctype.prepared_report import prepared_report
from frappe.core.doctype.report.report import Report
from frappe.desk import query_report
from frappe.utils.background_jobs import execute_job

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
FREE_BUILDER_REPORT = "AR Test Free Builder Report"
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
	ensure_report(FREE_BUILDER_REPORT, FREE_DOCTYPE, "Report Builder")
	ensure_report(SCRIPT_REPORT, DOCTYPE, "Script Report", report_script=SAFE_LOOKING_SCRIPT)
	# Committed on purpose: the request uses another connection.
	frappe.db.commit()  # nosemgrep: frappe-request-commit


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


class TestWhichReportRuns(ReportRulesTestCase):
	"""The gate must decide on the report Frappe really runs.

	Frappe follows `reference_report` only for a report of type "Custom Report"
	(`frappe/desk/query_report.py:232`). A report whose type was changed can keep an old value
	in that field. Frappe then runs the report itself, and so must the gate.
	"""

	STALE = "AR Test Stale Reference Report"
	CUSTOM = "AR Test Custom Report"
	CUSTOM_OF_CUSTOM = "AR Test Custom Of Custom Report"
	BROKEN = "AR Test Broken Custom Report"
	LOOP_A = "AR Test Loop A Report"
	LOOP_B = "AR Test Loop B Report"
	ALL = (STALE, CUSTOM, CUSTOM_OF_CUSTOM, BROKEN, LOOP_A, LOOP_B)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		query = f"select name as `Name:Data:200`, title as `Title:Data:200` from `tab{DOCTYPE}`"
		# A query report that was once a custom report of an ungoverned list report.
		ensure_report(cls.STALE, FREE_DOCTYPE, query=query)
		for name in (cls.CUSTOM, cls.CUSTOM_OF_CUSTOM, cls.BROKEN, cls.LOOP_A, cls.LOOP_B):
			ensure_report(name, FREE_DOCTYPE, "Custom Report", reference_report=NAME_REPORT)
		# Frappe checks links on save, so the odd states are written straight to the table.
		for name, reference in (
			(cls.STALE, FREE_BUILDER_REPORT),
			(cls.CUSTOM, NAME_REPORT),
			(cls.CUSTOM_OF_CUSTOM, cls.CUSTOM),
			(cls.BROKEN, "AR Test Report That Does Not Exist"),
			(cls.LOOP_A, cls.LOOP_B),
			(cls.LOOP_B, cls.LOOP_A),
		):
			frappe.db.set_value("Report", name, "reference_report", reference)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def setUp(self):
		super().setUp()
		self.addCleanup(self.cleanup)

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("Auto Email Report")
		frappe.db.delete("Prepared Report")
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_stale_reference_does_not_hide_a_query_report(self):
		"""Frappe runs the query. The leftover reference to a harmless list report means nothing."""
		for user in (EMPLOYEE_1, HR, NO_RULE):
			with self.subTest(user=user):
				self.assert_refused(self.run_report(self.login(user), self.STALE))
		self.assertTrue(reports.touches_governed(self.STALE))

	def test_system_manager_still_runs_the_report_with_a_stale_reference(self):
		response = self.run_report(self.login(ADMIN), self.STALE)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		self.assertIn(self.records[EMPLOYEE_1], response.get_data(as_text=True))

	def test_export_follows_the_same_decision(self):
		body = {"report_name": self.STALE, "file_format_type": "CSV", "filters": "{}"}

		self.assert_refused(self.send(self.login(HR), "POST", EXPORT, body=body))

	def test_custom_report_is_decided_by_the_report_it_refers_to(self):
		for report in (self.CUSTOM, self.CUSTOM_OF_CUSTOM):
			with self.subTest(report=report):
				self.assert_refused(self.run_report(self.login(HR), report))
				allowed = self.run_report(self.login(ADMIN), report)
				self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True)[:300])

	def test_missing_reference_is_refused(self):
		for user in (EMPLOYEE_1, HR, ADMIN):
			with self.subTest(user=user):
				self.assertTrue(self.denied(self.BROKEN, user))
		response = self.run_report(self.login(HR), self.BROKEN)
		self.assertNotEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		self.assert_refused(response, (403, 404, 417))
		self.assertTrue(reports.touches_governed(self.BROKEN))

	def test_reference_loop_is_refused_without_hanging(self):
		for report in (self.LOOP_A, self.LOOP_B):
			for user in (HR, ADMIN):
				with self.subTest(report=report, user=user):
					self.assertTrue(self.denied(report, user))
			self.assertTrue(reports.touches_governed(report))

	def test_prepared_report_gate_uses_the_report_that_runs(self):
		for report in (self.STALE, self.CUSTOM, self.BROKEN, self.LOOP_A):
			with self.subTest(report=report):
				frappe.set_user(ADMIN)
				doc = frappe.get_doc({"doctype": "Prepared Report", "report_name": report})
				self.assertRaises(frappe.PermissionError, doc.insert, ignore_permissions=True)
				frappe.set_user("Administrator")
		response = self.send(
			self.login(ADMIN), "POST", PREPARED + "make_prepared_report", body={"report_name": self.STALE}
		)
		self.assert_refused(response)
		self.assertFalse(frappe.db.count("Prepared Report"))

	def test_auto_email_report_gate_uses_the_report_that_runs(self):
		for report in (self.STALE, self.CUSTOM, self.BROKEN, self.LOOP_A):
			with self.subTest(report=report):
				doc = frappe.get_doc(
					{
						"doctype": "Auto Email Report",
						"report": report,
						"report_type": "Query Report",
						"user": ADMIN,
						"enabled": 1,
						"email_to": "ar.reader@example.test",
						"format": "CSV",
						"frequency": "Daily",
					}
				)
				frappe.set_user(ADMIN)
				self.assertRaises(frappe.PermissionError, doc.validate)
				self.assertRaises(frappe.PermissionError, doc.get_report_content)
				frappe.set_user("Administrator")
		client = self.login(ADMIN)
		body = {"report": self.STALE, "user": ADMIN, "email_to": "ar.reader@example.test", "format": "CSV"}
		response = self.send(
			client, "POST", "/api/v2/document/Auto Email Report", body={**body, "frequency": "Daily"}
		)
		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertFalse(frappe.db.count("Auto Email Report"))


class TestReportsWithoutRules(ReportRulesTestCase):
	"""With no governed document type the gate only keeps the field level of the report's own type."""

	RULES = ()

	def test_query_report_runs_for_a_user_with_role_permission(self):
		response = self.run_report(self.login(HR), NAME_REPORT)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])

	def test_restricted_field_still_needs_its_level(self):
		frappe.db.set_value(DOCTYPE, self.records[EMPLOYEE_1], "salary_amount", SALARY)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

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
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

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
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		return doc.name, file.name, file.file_url

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("DocShare", {"share_doctype": "File"})
		frappe.db.delete("File", {"attached_to_doctype": "Prepared Report"})
		frappe.db.delete("Prepared Report", {"report_name": NAME_REPORT})
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

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
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

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


class TestQueuedPreparedReport(ReportRulesTestCase):
	"""A Prepared Report queued before the rule existed is refused when its job starts.

	The check runs before Frappe's job function, for every report type. A list report never
	reaches the gate inside the Report document (`frappe/desk/query_report.py:93`).
	"""

	JOB = "frappe.core.doctype.prepared_report.prepared_report.generate_report"
	QUEUED_REPORTS = (NAME_REPORT, SCRIPT_REPORT, BUILDER_REPORT)

	def setUp(self):
		super().setUp()
		self.addCleanup(self.cleanup)

	def queued(self, report: str) -> str:
		doc = frappe.get_doc(doctype="Prepared Report", report_name=report, status="Queued")
		doc.name = frappe.generate_hash(length=10)
		doc.owner = ADMIN
		doc.db_insert()
		# Committed on purpose: the job reads committed data.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		return doc.name

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		if hasattr(frappe.local, "job"):
			del frappe.local.job
		frappe.db.delete("File", {"attached_to_doctype": "Prepared Report"})
		frappe.db.delete("Prepared Report")
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def run_job(self, prepared: str) -> None:
		"""Run the queued job the way a worker does, as the System Manager who queued it."""
		execute_job(
			frappe.local.site,
			self.JOB,
			None,
			"ar-test-prepared-report",
			{"prepared_report": prepared},
			user=ADMIN,
			is_async=False,
		)

	def set_rules_active(self, active: int) -> None:
		frappe.set_user("Administrator")
		for name in self.rules.values():
			rule = frappe.get_doc("Access Rule", name)
			rule.is_active = active
			rule.save()
		# Committed on purpose: the job reads committed data.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def files_of(self, prepared: str) -> int:
		return frappe.db.count(
			"File", {"attached_to_doctype": "Prepared Report", "attached_to_name": prepared}
		)

	def test_before_job_hook_is_registered(self):
		self.assertIn(
			"platform_core.erisim.reports.refuse_prepared_report_job", frappe.get_hooks("before_job")
		)

	def test_job_is_refused_before_frappe_starts_it(self):
		for report in self.QUEUED_REPORTS:
			prepared = self.queued(report)
			with self.subTest(report=report):
				with (
					patch.object(prepared_report, "generate_report") as generate,
					patch.object(Report, "execute_query_report") as query,
					patch.object(Report, "execute_script_report") as script,
				):
					self.assertRaises(frappe.PermissionError, self.run_job, prepared)
				generate.assert_not_called()
				query.assert_not_called()
				script.assert_not_called()
				frappe.set_user("Administrator")
				self.assertEqual(self.files_of(prepared), 0)
				self.assertEqual(frappe.db.get_value("Prepared Report", prepared, "status"), "Error")

	def test_direct_call_of_the_job_function_writes_no_file(self):
		"""Code that calls Frappe's function without a worker still cannot store a result."""
		for report in self.QUEUED_REPORTS:
			prepared = self.queued(report)
			with self.subTest(report=report):
				frappe.set_user(ADMIN)
				with patch.object(Report, "execute_script"):
					prepared_report.generate_report(prepared)
				frappe.set_user("Administrator")
				self.assertEqual(self.files_of(prepared), 0)
				self.assertNotEqual(frappe.db.get_value("Prepared Report", prepared, "status"), "Completed")

	def test_job_for_ungoverned_data_is_not_refused(self):
		self.addCleanup(self.set_rules_active, 1)
		self.set_rules_active(0)
		prepared = self.queued(NAME_REPORT)

		self.run_job(prepared)

		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Prepared Report", prepared, "status"), "Completed")
		self.assertEqual(self.files_of(prepared), 1)

	def test_live_run_by_a_system_manager_still_works(self):
		"""Only the prepared path is closed. The System Manager can still run the report directly."""
		frappe.set_user(ADMIN)

		result = query_report.run(NAME_REPORT, {}, ignore_prepared_report=True)

		self.assertTrue(result["result"])
