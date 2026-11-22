"""Tests of the query report gate (decision note, section 9). The security gate requires this file name."""

import frappe

from platform_core.erisim.tests.base import ADMIN, DOCTYPE, EMPLOYEE_1, HR, MANAGER_1, NO_RULE, ErisimTestCase

QUERY_REPORT = "ER Test Sorgu Raporu"
RUN = "/api/method/frappe.desk.query_report.run"
EXPORT = "/api/method/frappe.desk.query_report.export_query"


class TestQueryReportGate(ErisimTestCase):
	"""A query report reads with its own SQL. The gate denies a narrowed user (decision note, section 9)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Report", QUERY_REPORT):
			frappe.get_doc(
				doctype="Report",
				report_name=QUERY_REPORT,
				ref_doctype=DOCTYPE,
				report_type="Query Report",
				is_standard="No",
				query=f"select name as `Name:Data:200`, title as `Title:Data:200` from `tab{DOCTYPE}`",
			).insert()
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def run_report(self, client):
		return self.send(client, "POST", RUN, body={"report_name": QUERY_REPORT, "filters": "{}"})

	def test_run_foreign_data_denied(self):
		"""A user whose records are narrowed cannot run the query report."""
		for user in (EMPLOYEE_1, MANAGER_1, NO_RULE):
			with self.subTest(user=user):
				response = self.run_report(self.login(user))

				self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
				for name in self.records.values():
					self.assertNotIn(name, response.get_data(as_text=True))

	def test_export_query_foreign_data_denied(self):
		response = self.send(
			self.login(EMPLOYEE_1),
			"POST",
			EXPORT,
			body={"report_name": QUERY_REPORT, "file_format_type": "CSV", "filters": "{}"},
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		for name in self.records.values():
			self.assertNotIn(name, response.get_data(as_text=True))

	def test_run_guest_denied(self):
		response = self.run_report(self.anonymous())

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		for name in self.records.values():
			self.assertNotIn(name, response.get_data(as_text=True))

	def test_export_query_guest_denied(self):
		response = self.send(
			self.anonymous(),
			"POST",
			EXPORT,
			body={"report_name": QUERY_REPORT, "file_format_type": "CSV", "filters": "{}"},
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		for name in self.records.values():
			self.assertNotIn(name, response.get_data(as_text=True))

	def test_user_who_sees_every_record_is_refused_too(self):
		"""What the SQL of a query report reads cannot be verified. Only a System Manager runs it."""
		response = self.run_report(self.login(HR))

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_system_manager_runs_query_report(self):
		response = self.run_report(self.login(ADMIN))

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		body = response.get_data(as_text=True)
		for name in self.records.values():
			self.assertIn(name, body)

	def test_python_caller_reaches_the_gate_through_frappe_override(self):
		"""Decision note, section 9: the caller finds the function with `frappe.override_whitelisted_method`."""
		frappe.set_user(EMPLOYEE_1)
		run = frappe.get_attr(frappe.override_whitelisted_method("frappe.desk.query_report.run"))

		self.assertRaises(frappe.PermissionError, run, report_name=QUERY_REPORT, filters={})
