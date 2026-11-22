"""Veri yüzeyleri: liste, kayıt, liste raporu ve dışa aktarma aynı kümeyi verir (G-121)."""

import csv
import io
import json

from platform_core.erisim.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	EXPECTED_VISIBLE,
	MANAGER_1,
	ErisimTestCase,
)


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
