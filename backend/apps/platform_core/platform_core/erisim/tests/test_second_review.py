"""Findings of the second independent review. Each test class covers one finding."""

import json

import frappe
from frappe.core.doctype.prepared_report.prepared_report import generate_report
from frappe.tests.test_api import make_request

from platform_core.erisim import rules
from platform_core.erisim.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	HR,
	MANAGER_1,
	REST,
	ROLE_EMPLOYEE,
	ROLE_MANAGER,
	RULE_DOCTYPE,
	ErisimTestCase,
)

DOWNLOAD = "/api/method/frappe.core.doctype.prepared_report.prepared_report.download_attachment"
RUN = "/api/method/frappe.desk.query_report.run"
EXPORT = "/api/method/frappe.desk.query_report.export_query"
PREPARED_ROLE = "Prepared Report User"
NAME_REPORT = "AR Test Name Report"
SALARY_REPORT = "AR Test Salary Report"
SALARY = 987651


def ensure_report(name: str, columns: str) -> None:
	if not frappe.db.exists("Report", name):
		frappe.get_doc(
			doctype="Report",
			report_name=name,
			ref_doctype=DOCTYPE,
			report_type="Query Report",
			is_standard="No",
			query=f"select {columns} from `tab{DOCTYPE}`",
		).insert()


class TestPreparedReportDownload(ErisimTestCase):
	"""Finding 1: a prepared report made for someone else must not be downloadable by a narrowed user."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_report(NAME_REPORT, "name as `Name:Data:200`, title as `Title:Data:200`")
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def setUp(self):
		super().setUp()
		self.addCleanup(self.cleanup)
		frappe.get_doc("User", EMPLOYEE_1).add_roles(PREPARED_ROLE)
		prepared = frappe.get_doc({"doctype": "Prepared Report", "report_name": NAME_REPORT}).insert()
		generate_report(prepared.name)
		self.prepared = prepared.name
		self.assertEqual(frappe.db.get_value("Prepared Report", self.prepared, "status"), "Completed")
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def cleanup(self) -> None:
		frappe.set_user("Administrator")
		frappe.get_doc("User", EMPLOYEE_1).remove_roles(PREPARED_ROLE)
		for name in frappe.get_all("Prepared Report", filters={"report_name": NAME_REPORT}, pluck="name"):
			frappe.delete_doc("Prepared Report", name, force=True)
		frappe.db.commit()  # nosemgrep

	def assert_no_record_leaks(self, response) -> None:
		body = response.get_data(as_text=True)
		for name in self.records.values():
			self.assertNotIn(name, body)

	def test_narrowed_user_cannot_download_a_report_prepared_by_an_admin(self):
		response = self.send(self.login(EMPLOYEE_1), "GET", DOWNLOAD, query={"dn": self.prepared})

		# Frappe reports this refusal as a validation error (417), not as 403.
		self.assertIn(response.status_code, (403, 417), response.get_data(as_text=True)[:300])
		self.assert_no_record_leaks(response)

	def test_narrowed_user_cannot_read_the_prepared_report_file(self):
		file_url = frappe.db.get_value(
			"File", {"attached_to_doctype": "Prepared Report", "attached_to_name": self.prepared}, "file_url"
		)
		self.assertTrue(file_url)

		response = self.send(self.login(EMPLOYEE_1), "GET", file_url)

		self.assertEqual(response.status_code, 403)

	def test_narrowed_user_cannot_read_the_prepared_report_through_run(self):
		response = self.send(
			self.login(EMPLOYEE_1),
			"POST",
			RUN,
			body={"report_name": NAME_REPORT, "filters": "{}", "prepared_report_name": self.prepared},
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assert_no_record_leaks(response)

	def test_user_who_sees_every_record_downloads_the_report(self):
		frappe.get_doc("User", HR).add_roles(PREPARED_ROLE)
		self.addCleanup(lambda: frappe.get_doc("User", HR).remove_roles(PREPARED_ROLE))
		frappe.db.commit()  # nosemgrep

		response = self.send(self.login(HR), "GET", DOWNLOAD, query={"dn": self.prepared})

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])


class TestReportFieldLevel(ErisimTestCase):
	"""Finding 2: seeing every record does not allow a report to return a restricted field."""

	RULES = (
		{"title": "Manager all records", "role": ROLE_MANAGER, "scope": "all", "allow_read": 1},
		{"title": "HR all records", "role": "ER IK", "scope": "all", "allow_read": 1},
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_report(SALARY_REPORT, "name as `Name:Data:200`, salary_amount as `Salary:Currency:120`")
		frappe.db.set_value(DOCTYPE, cls.records[EMPLOYEE_1], "salary_amount", SALARY)
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def run_report(self, client):
		return self.send(client, "POST", RUN, body={"report_name": SALARY_REPORT, "filters": "{}"})

	def export_report(self, client):
		body = {"report_name": SALARY_REPORT, "file_format_type": "CSV", "filters": "{}"}
		return self.send(client, "POST", EXPORT, body=body)

	def test_manager_sees_every_record_on_the_list(self):
		"""The manager really is unrestricted by record. Only the field level differs."""
		self.assertEqual(self.listed_names(self.login(MANAGER_1)), set(self.records.values()))

	def test_user_without_field_level_cannot_run_the_report(self):
		response = self.run_report(self.login(MANAGER_1))

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertNotIn(str(SALARY), response.get_data(as_text=True))

	def test_user_without_field_level_cannot_export_the_report(self):
		response = self.export_report(self.login(MANAGER_1))

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertNotIn(str(SALARY), response.get_data(as_text=True))

	def test_user_with_field_level_runs_the_report(self):
		response = self.run_report(self.login(HR))

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		self.assertIn(str(SALARY), response.get_data(as_text=True))


class TestStaleReader(ErisimTestCase):
	"""Finding 3: a request that read the old rules must not hand them to later requests."""

	OWN_RULE = "Calisan kendi kaydi"

	def raw_request(self, client, method: str, path: str, body=None):
		"""Send a request without committing or rolling back this test's own connection."""
		kwargs = {"path": path, "method": method, "headers": {"Accept": "application/json"}}
		if body is not None:
			kwargs["headers"]["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		return make_request(client.open, args=(), kwargs=kwargs, site=self.site)

	def restore(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		rule = frappe.get_doc(RULE_DOCTYPE, self.rules[self.OWN_RULE])
		rule.update({"is_active": 1})
		rule.save()
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def test_reader_with_an_old_snapshot_cannot_restore_a_removed_permission(self):
		admin = self.login("er.admin@example.test")
		employee = self.login(EMPLOYEE_1)
		own = self.records[EMPLOYEE_1]
		self.addCleanup(self.restore)
		frappe.db.commit()  # nosemgrep: start a fresh snapshot for the slow reader

		# The slow reader opens its snapshot while the rule still grants access.
		self.assertTrue(any(rule["role"] == ROLE_EMPLOYEE for rule in rules.rules_for(DOCTYPE)))

		# Another request removes the permission and commits.
		path = f"{REST}{RULE_DOCTYPE}/{self.rules[self.OWN_RULE]}"
		changed = self.raw_request(admin, "PUT", path, {"is_active": 0})
		self.assertEqual(changed.status_code, 200, changed.get_data(as_text=True)[:300])

		# The slow reader looks the rules up again from its old snapshot, as a cache miss would.
		frappe.local.cache = {}
		if getattr(frappe.local, "request_cache", None) is not None:
			frappe.local.request_cache.clear()
		rules.rules_for(DOCTYPE)

		# The next request must already be denied.
		response = self.raw_request(employee, "GET", f"{REST}{DOCTYPE}/{own}")
		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
