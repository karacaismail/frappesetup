"""Findings of the third independent review and the orchestrator's decisions on them.

1. A prepared report file is checked against the reader's current access on every read.
2. An Auto Email Report that touches a governed document type cannot be saved or run.
3. A report of unknown scope does not run for a narrowed user. A declared scope is enforced per
   document type and field.
4. A background export re-checks access when the job runs.
"""

from unittest.mock import patch

import frappe
import frappe.share
from frappe.core.doctype.prepared_report.prepared_report import generate_report
from frappe.desk import query_report
from frappe.email.doctype.auto_email_report import auto_email_report

from platform_core.erisim import reports
from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	FREE_DOCTYPE,
	HR,
	MANAGER_1,
	NO_RULE,
	ROLE_HR,
	ROLE_MANAGER,
	RULE_DOCTYPE,
	ErisimTestCase,
)

RUN = "/api/method/frappe.desk.query_report.run"
PREPARED_ROLE = "Prepared Report User"
NAME_REPORT = "AR Test Name Report"
CROSS_REPORT = "AR Test Cross Type Report"
SALARY_CROSS_REPORT = "AR Test Cross Type Salary Report"
FREE_REPORT = "AR Test Free Report"
BUILDER_REPORT = "AR Test Builder Report"
HR_RULE = "IK tum kayitlar"
SALARY = 987652


def ensure_report(name: str, ref_doctype: str, query: str | None, report_type: str = "Query Report") -> None:
	if not frappe.db.exists("Report", name):
		frappe.get_doc(
			doctype="Report",
			report_name=name,
			ref_doctype=ref_doctype,
			report_type=report_type,
			is_standard="No",
			query=query,
		).insert()


def ensure_reports() -> None:
	columns = "name as `Name:Data:200`, title as `Title:Data:200`"
	ensure_report(NAME_REPORT, DOCTYPE, f"select {columns} from `tab{DOCTYPE}`")
	# The report belongs to an ungoverned type but reads the governed one.
	ensure_report(CROSS_REPORT, FREE_DOCTYPE, f"select {columns} from `tab{DOCTYPE}`")
	ensure_report(
		SALARY_CROSS_REPORT,
		FREE_DOCTYPE,
		f"select name as `Name:Data:200`, salary_amount as `Salary:Currency:120` from `tab{DOCTYPE}`",
	)
	ensure_report(FREE_REPORT, FREE_DOCTYPE, f"select {columns} from `tab{FREE_DOCTYPE}`")
	ensure_report(BUILDER_REPORT, DOCTYPE, None, "Report Builder")
	frappe.db.commit()  # nosemgrep: the request uses another connection


class ReviewTestCase(ErisimTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_reports()

	def set_rule_active(self, title: str, active: int) -> None:
		frappe.set_user("Administrator")
		rule = frappe.get_doc(RULE_DOCTYPE, self.rules[title])
		rule.is_active = active
		rule.save()
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def run_report(self, client, report: str):
		return self.send(client, "POST", RUN, body={"report_name": report, "filters": "{}"})

	def assert_no_record_leaks(self, response) -> None:
		body = response.get_data(as_text=True)
		for name in self.records.values():
			self.assertNotIn(name, body)


class TestPreparedReportFile(ReviewTestCase):
	"""Decision 1: neither file ownership nor a file share outlives the reader's access."""

	def setUp(self):
		super().setUp()
		self.addCleanup(self.cleanup)
		frappe.get_doc("User", HR).add_roles(PREPARED_ROLE)
		frappe.db.commit()  # nosemgrep: the request uses another connection
		frappe.set_user(HR)
		# Frappe's own endpoint inserts the record this way after checking the report role.
		prepared = frappe.get_doc({"doctype": "Prepared Report", "report_name": NAME_REPORT})
		prepared.insert(ignore_permissions=True)
		generate_report(prepared.name)
		frappe.set_user("Administrator")
		self.prepared = prepared.name
		file = frappe.db.get_value(
			"File",
			{"attached_to_doctype": "Prepared Report", "attached_to_name": self.prepared},
			["name", "file_url", "owner"],
			as_dict=True,
		)
		self.assertEqual(file.owner, HR)
		self.file, self.file_url = file.name, file.file_url
		frappe.db.commit()  # nosemgrep

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self.set_rule_active(HR_RULE, 1)
		frappe.get_doc("User", HR).remove_roles(PREPARED_ROLE)
		frappe.db.delete("DocShare", {"share_doctype": "File"})
		for name in frappe.get_all("Prepared Report", filters={"report_name": NAME_REPORT}, pluck="name"):
			frappe.delete_doc("Prepared Report", name, force=True)
		frappe.db.commit()  # nosemgrep

	def test_owner_reads_the_file_while_access_lasts(self):
		response = self.send(self.login(HR), "GET", self.file_url)

		self.assertEqual(response.status_code, 200)

	def test_owner_cannot_read_the_file_after_losing_access(self):
		client = self.login(HR)

		self.set_rule_active(HR_RULE, 0)

		self.assertEqual(self.send(client, "GET", self.file_url).status_code, 403)

	def test_file_share_does_not_open_the_file_to_a_narrowed_user(self):
		frappe.share.add_docshare("File", self.file, EMPLOYEE_1, read=1)
		frappe.db.commit()  # nosemgrep: the request uses another connection

		response = self.send(self.login(EMPLOYEE_1), "GET", self.file_url)

		self.assertEqual(response.status_code, 403)


class TestAutoEmailReport(ReviewTestCase):
	"""Decision 2: no Auto Email Report on governed data. Scheduled jobs are not wanted (D-6)."""

	def auto_report(self, report: str, report_type: str = "Query Report"):
		return frappe.get_doc(
			doctype="Auto Email Report",
			report=report,
			report_type=report_type,
			user="Administrator",
			enabled=1,
			email_to="ar.reader@example.test",
			format="CSV",
			frequency="Daily",
		)

	def insert_unchecked(self, report: str) -> str:
		"""Stand-in for a record that was saved before the document type became governed."""
		doc = self.auto_report(report)
		doc.name = report
		doc.db_insert()
		self.addCleanup(frappe.db.delete, "Auto Email Report", {"name": doc.name})
		return doc.name

	def test_cannot_be_saved_for_a_governed_document_type(self):
		for report, report_type in (
			(NAME_REPORT, "Query Report"),
			(CROSS_REPORT, "Query Report"),
			(BUILDER_REPORT, "Report Builder"),
		):
			with self.subTest(report=report):
				self.assertRaises(frappe.PermissionError, self.auto_report(report, report_type).insert)
		self.assertFalse(frappe.db.count("Auto Email Report"))

	def test_existing_one_cannot_be_downloaded_or_sent(self):
		name = self.insert_unchecked(NAME_REPORT)

		self.assertRaises(frappe.PermissionError, auto_email_report.download, name)
		self.assertRaises(frappe.PermissionError, auto_email_report.send_now, name)
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Auto Email Report", name).send)

	def test_declared_report_on_ungoverned_types_is_not_refused(self):
		with patch.object(reports, "declared_scope", return_value={FREE_DOCTYPE: ["name", "title"]}):
			content = self.auto_report(FREE_REPORT).get_report_content()

		self.assertNotIn(self.records[EMPLOYEE_1], str(content))


class TestReportScope(ReviewTestCase):
	"""Decision 3: unknown scope is refused; a declared scope is enforced per type and field."""

	RULES = (
		*ErisimTestCase.RULES,
		{"title": "Manager all records", "role": ROLE_MANAGER, "scope": "all", "allow_read": 1},
	)

	def test_undeclared_report_that_reads_another_type_is_refused_for_narrowed_users(self):
		for user in (EMPLOYEE_1, NO_RULE):
			with self.subTest(user=user):
				response = self.run_report(self.login(user), CROSS_REPORT)

				self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
				self.assert_no_record_leaks(response)

	def test_undeclared_report_runs_for_a_user_who_sees_all_governed_data(self):
		response = self.run_report(self.login(HR), CROSS_REPORT)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])

	def test_undeclared_report_is_refused_without_every_field_level(self):
		"""The manager sees every record but not the salary level. Unknown scope may read it."""
		response = self.run_report(self.login(MANAGER_1), CROSS_REPORT)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])

	def test_declared_scope_lets_a_user_with_the_declared_fields_run_the_report(self):
		with patch.object(reports, "declared_scope", return_value={DOCTYPE: ["name", "title"]}):
			response = self.run_report(self.login(MANAGER_1), CROSS_REPORT)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])

	def test_declared_restricted_field_is_refused_without_its_level(self):
		frappe.db.set_value(DOCTYPE, self.records[EMPLOYEE_1], "salary_amount", SALARY)
		frappe.db.commit()  # nosemgrep: the request uses another connection
		scope = {DOCTYPE: ["name", "salary_amount"]}

		with patch.object(reports, "declared_scope", return_value=scope):
			refused = self.run_report(self.login(MANAGER_1), SALARY_CROSS_REPORT)
			allowed = self.run_report(self.login(HR), SALARY_CROSS_REPORT)

		self.assertEqual(refused.status_code, 403, refused.get_data(as_text=True)[:300])
		self.assertNotIn(str(SALARY), refused.get_data(as_text=True))
		self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True)[:300])

	def test_declared_governed_type_still_refuses_a_narrowed_user(self):
		with patch.object(reports, "declared_scope", return_value={DOCTYPE: ["name", "title"]}):
			response = self.run_report(self.login(EMPLOYEE_1), CROSS_REPORT)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assert_no_record_leaks(response)

	def test_declared_scope_requires_role_permission_on_every_declared_type(self):
		with patch.object(reports, "declared_scope", return_value={RULE_DOCTYPE: ["name"]}):
			response = self.run_report(self.login(HR), CROSS_REPORT)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])

	def test_python_caller_is_refused_without_any_endpoint(self):
		"""The gate sits on the Report document, so code that calls Frappe directly meets it too."""
		frappe.set_user(EMPLOYEE_1)

		self.assertRaises(frappe.PermissionError, query_report.run, CROSS_REPORT, {})
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Report", NAME_REPORT).get_data)


class TestBackgroundExport(ReviewTestCase):
	"""Decision 4: the export job checks access when it runs, not only when it is queued."""

	def job_arguments(self):
		form = frappe._dict(report_name=NAME_REPORT, file_format_type="CSV", filters="{}")
		return "ar.reader@example.test", form, {}

	def test_job_refuses_a_narrowed_user(self):
		frappe.set_user(EMPLOYEE_1)

		self.assertRaises(frappe.PermissionError, query_report.run_export_query_job, *self.job_arguments())

	def test_job_refuses_a_user_whose_access_was_removed_after_queueing(self):
		self.addCleanup(self.set_rule_active, HR_RULE, 1)
		queued = self.job_arguments()

		self.set_rule_active(HR_RULE, 0)
		frappe.set_user(HR)

		self.assertRaises(frappe.PermissionError, query_report.run_export_query_job, *queued)
