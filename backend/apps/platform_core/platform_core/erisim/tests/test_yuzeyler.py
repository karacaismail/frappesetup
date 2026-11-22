"""Veri yüzeyleri: liste, kayıt, liste raporu ve dışa aktarma aynı kümeyi verir (G-121)."""

import csv
import io
import json

import frappe

from platform_core.erisim.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	EXPECTED_VISIBLE,
	HR,
	MANAGER_1,
	NO_RULE,
	ErisimTestCase,
)

QUERY_REPORT = "ER Test Sorgu Raporu"
RUN = "/api/method/frappe.desk.query_report.run"
EXPORT = "/api/method/frappe.desk.query_report.export_query"


class TestSurfaces(ErisimTestCase):
	def report_view_names(self, client) -> set[str]:
		"""Liste raporu (“Report Builder”) yüzeyi."""
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.desk.reportview.get",
			body={"doctype": DOCTYPE, "fields": json.dumps([f"`tab{DOCTYPE}`.`name`"]), "page_length": 500},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		message = response.json.get("message") or {}
		if not message:
			return set()
		position = message["keys"].index("name")
		return {row[position] for row in message["values"]}

	def report_view_count(self, client) -> int:
		response = self.send(
			client, "POST", "/api/method/frappe.desk.reportview.get_count", body={"doctype": DOCTYPE}
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["message"]

	def exported_names(self, client) -> set[str]:
		"""Liste dışa aktarması yüzeyi. İlk satır başlıktır."""
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.desk.reportview.export_query",
			body={
				"doctype": DOCTYPE,
				"fields": json.dumps([f"`tab{DOCTYPE}`.`name`"]),
				"file_format_type": "CSV",
				"title": DOCTYPE,
				"page_length": 500,
			},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		rows = list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip("﻿"))))
		known = set(self.records.values())
		return {cell for row in rows[1:] for cell in row if cell in known}

	def link_search_names(self, client) -> set[str]:
		"""Bağlantı araması yüzeyi."""
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.desk.search.search_link",
			body={"doctype": DOCTYPE, "txt": "", "page_length": 500},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return {row["value"] for row in response.json["message"]}

	def test_every_surface_returns_the_same_records_for_every_user(self):
		for user, owners in EXPECTED_VISIBLE.items():
			expected = self.names_of(owners)
			client = self.login(user)
			with self.subTest(user=user, surface="liste"):
				self.assertEqual(self.listed_names(client), expected)
			with self.subTest(user=user, surface="kayit"):
				self.assertEqual(self.readable_names(client), expected)
			with self.subTest(user=user, surface="liste raporu"):
				self.assertEqual(self.report_view_names(client), expected)
			with self.subTest(user=user, surface="sayim"):
				self.assertEqual(self.report_view_count(client), len(expected))
			with self.subTest(user=user, surface="disa aktarma"):
				self.assertEqual(self.exported_names(client), expected)
			with self.subTest(user=user, surface="baglanti aramasi"):
				self.assertEqual(self.link_search_names(client), expected)

	def test_print_follows_the_document_decision(self):
		client = self.login(EMPLOYEE_1)
		path = "/api/method/frappe.utils.print_format.download_pdf"
		other = self.records[MANAGER_1]

		response = self.send(client, "GET", path, query={"doctype": DOCTYPE, "name": other})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))


class TestQueryReportGate(ErisimTestCase):
	"""Sorgu raporu kendi SQL'iyle okur. Kapı daraltılmış kullanıcıyı reddeder (karar notu 9. bölüm)."""

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
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır

	def run_report(self, client):
		return self.send(client, "POST", RUN, body={"report_name": QUERY_REPORT, "filters": "{}"})

	def test_narrowed_user_cannot_run_query_report(self):
		for user in (EMPLOYEE_1, MANAGER_1, NO_RULE):
			with self.subTest(user=user):
				response = self.run_report(self.login(user))

				self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
				for name in self.records.values():
					self.assertNotIn(name, response.get_data(as_text=True))

	def test_narrowed_user_cannot_export_query_report(self):
		response = self.send(
			self.login(EMPLOYEE_1),
			"POST",
			EXPORT,
			body={"report_name": QUERY_REPORT, "file_format_type": "CSV", "filters": "{}"},
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		for name in self.records.values():
			self.assertNotIn(name, response.get_data(as_text=True))

	def test_user_with_unfiltered_all_rule_runs_query_report(self):
		response = self.run_report(self.login(HR))

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		body = response.get_data(as_text=True)
		for name in self.records.values():
			self.assertIn(name, body)

	def test_python_caller_reaches_the_gate_through_frappe_override(self):
		"""Karar notu 9. bölüm: çağıran işlevi `frappe.override_whitelisted_method` ile bulur."""
		frappe.set_user(EMPLOYEE_1)
		run = frappe.get_attr(frappe.override_whitelisted_method("frappe.desk.query_report.run"))

		self.assertRaises(frappe.PermissionError, run, report_name=QUERY_REPORT, filters={})
