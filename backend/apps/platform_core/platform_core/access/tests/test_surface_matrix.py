"""The rest of the data surface matrix of G-121: every surface gives the decision of the list and the record.

`test_surfaces.py` covers the list, the record, the list report, the count, the export and the link search.
This file covers the surfaces it leaves out: realtime rooms, print, global search, files and
attachments, the Data Import export, the AI tool layer, and the level 1 field on every surface.
Every test calls the surface over HTTP without a user interface (D-6). The matrix is in
`docs/access-surface-matrix.md`.
"""

import csv
import io
import json

import frappe
from frappe.query_builder import Table

from platform_core.access import files
from platform_core.access.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	EXPECTED_VISIBLE,
	HR,
	MANAGER_1,
	MANAGER_2,
	AccessRuleTestCase,
)

# A salary value that cannot appear by chance in a record name or a date.
SALARY = 73191
SALARY_TEXT = "73191"
SEARCH_WORD = "matrixsurfaceword"
MCP_PATH = "/api/method/platform_core.api.ai.mcp"


class SurfaceMatrixTestCase(AccessRuleTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for name in cls.records.values():
			# Test setup as the administrator: the value is written on purpose without a permission check.
			frappe.db.set_value(DOCTYPE, name, "salary_amount", SALARY, update_modified=False)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit


class TestRealtimeRooms(SurfaceMatrixTestCase):
	"""The realtime server asks `frappe.realtime.has_permission` before it lets a socket into a room."""

	def room_answer(self, client, name: str):
		return self.send(
			client,
			"GET",
			"/api/method/frappe.realtime.has_permission",
			query={"doctype": DOCTYPE, "name": name, "ptype": "read"},
		)

	def test_record_room_follows_the_record_decision(self):
		for user, owners in EXPECTED_VISIBLE.items():
			client = self.login(user)
			expected = self.names_of(owners)
			for name in self.records.values():
				with self.subTest(user=user, record=self.owner_of[name]):
					status = self.room_answer(client, name).status_code
					self.assertEqual(status, 200 if name in expected else 403)

	def test_guest_cannot_join_a_record_room(self):
		response = self.room_answer(self.anonymous(), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 403)

	def test_list_room_is_closed_to_a_narrowed_user(self):
		"""The list room gets `list_update` for every record with its name and its editor.

		A user whom a rule narrows would learn about records outside the rule. So the room is closed to them.
		"""
		for user in (EMPLOYEE_1, MANAGER_1, MANAGER_2):
			with self.subTest(user=user):
				self.assertEqual(self.room_answer(self.login(user), "").status_code, 403)

	def test_list_room_stays_open_to_a_user_who_sees_every_record(self):
		self.assertEqual(self.room_answer(self.login(HR), "").status_code, 200)


class TestPrint(SurfaceMatrixTestCase):
	def print_html(self, client, name: str):
		return self.send(
			client,
			"POST",
			"/api/method/frappe.www.printview.get_html_and_style",
			body={"doc": DOCTYPE, "name": name, "print_format": "Standard"},
		)

	def test_print_html_follows_the_record_decision(self):
		for user, owners in EXPECTED_VISIBLE.items():
			client = self.login(user)
			expected = self.names_of(owners)
			for name in self.records.values():
				with self.subTest(user=user, record=self.owner_of[name]):
					status = self.print_html(client, name).status_code
					self.assertEqual(status, 200 if name in expected else 403)

	def test_print_page_refuses_a_record_outside_the_rule(self):
		client = self.login(EMPLOYEE_1)
		response = self.send(
			client, "GET", "/printview", query={"doctype": DOCTYPE, "name": self.records[MANAGER_1]}
		)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(SALARY_TEXT, response.get_data(as_text=True))

	def test_print_leaves_out_the_level_1_field(self):
		response = self.print_html(self.login(EMPLOYEE_1), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 200)
		self.assertNotIn(SALARY_TEXT, response.json["message"]["html"])

	def test_print_shows_the_level_1_field_to_a_role_with_the_level(self):
		response = self.print_html(self.login(HR), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 200)
		self.assertIn("73,191", response.json["message"]["html"])


class TestGlobalSearch(SurfaceMatrixTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_single("Global Search Settings")
		if DOCTYPE not in {row.document_type for row in settings.allowed_in_global_search}:
			settings.append("allowed_in_global_search", {"document_type": DOCTYPE})
			settings.save()
		index = Table("__global_search")
		for name in cls.records.values():
			frappe.qb.into(index).columns(
				index.doctype, index.name, index.title, index.content, index.published
			).insert(DOCTYPE, name, name, f"{SEARCH_WORD} {name}", 0).run()
		frappe.cache.hdel("global_search", "search_priorities")
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		index = Table("__global_search")
		frappe.qb.from_(index).delete().where(index.doctype == DOCTYPE).run()
		settings = frappe.get_single("Global Search Settings")
		settings.allowed_in_global_search = [
			row for row in settings.allowed_in_global_search if row.document_type != DOCTYPE
		]
		settings.save()
		frappe.cache.hdel("global_search", "search_priorities")
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	def found_names(self, client, **extra) -> set[str]:
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.utils.global_search.search",
			body={"text": SEARCH_WORD, "limit": 100, **extra},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return {row["name"] for row in response.json["message"] if row["doctype"] == DOCTYPE}

	def test_global_search_returns_the_records_of_the_list(self):
		for user, owners in EXPECTED_VISIBLE.items():
			with self.subTest(user=user):
				self.assertEqual(self.found_names(self.login(user)), self.names_of(owners))

	def test_global_search_in_one_document_type_returns_the_same(self):
		client = self.login(MANAGER_1)

		self.assertEqual(
			self.found_names(client, doctype=DOCTYPE), self.names_of(EXPECTED_VISIBLE[MANAGER_1])
		)


def file_text(name: str) -> bytes:
	"""Each attachment has its own content. Frappe gives files with the same content one shared address."""
	return f"g121 attachment of {name}".encode()


class TestFiles(SurfaceMatrixTestCase):
	"""A private attachment follows the decision on the record it is attached to."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.files = {}
		for name in cls.records.values():
			file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"g121-{name}.txt",
					"attached_to_doctype": DOCTYPE,
					"attached_to_name": name,
					"is_private": 1,
					"content": file_text(name),
				}
			).insert()
			cls.files[name] = (file.name, file.file_url)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for file_name, _url in cls.files.values():
			frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	def test_file_record_follows_the_record_decision(self):
		for user, owners in EXPECTED_VISIBLE.items():
			client = self.login(user)
			expected = self.names_of(owners)
			for name, (file_name, _url) in self.files.items():
				with self.subTest(user=user, record=self.owner_of[name]):
					status = self.rest_get(client, file_name, doctype="File").status_code
					self.assertEqual(status, 200 if name in expected else 403)

	def test_file_download_follows_the_record_decision(self):
		for user, owners in EXPECTED_VISIBLE.items():
			client = self.login(user)
			expected = self.names_of(owners)
			for name, (_file_name, url) in self.files.items():
				with self.subTest(user=user, record=self.owner_of[name]):
					response = self.send(client, "GET", url)
					if name in expected:
						self.assertEqual(response.status_code, 200)
						self.assertEqual(response.get_data(), file_text(name))
					else:
						self.assertEqual(response.status_code, 403)
						self.assertNotIn(file_text(name), response.get_data())

	def test_file_list_shows_no_attachment_of_a_record_outside_the_rule(self):
		client = self.login(EMPLOYEE_1)
		response = self.rest_list(
			client,
			doctype="File",
			fields=("name", "attached_to_name"),
			filters=[["attached_to_doctype", "=", DOCTYPE]],
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			{row["attached_to_name"] for row in response.json["data"]}
			- self.names_of(EXPECTED_VISIBLE[EMPLOYEE_1]),
			set(),
		)

	def test_file_list_condition_keeps_only_attachments_of_visible_records(self):
		"""The condition the engine adds to the file list, run in the database for every user."""
		table = frappe.qb.DocType("File")
		for user, owners in EXPECTED_VISIBLE.items():
			with self.subTest(user=user):
				query = (
					frappe.qb.from_(table)
					.select(table.attached_to_name)
					.where(table.attached_to_doctype == DOCTYPE)
					.where(files.list_criterion(user))
				)
				self.assertEqual({row[0] for row in query.run()}, self.names_of(owners))

	def test_attachments_of_a_record_outside_the_rule_are_not_loaded(self):
		client = self.login(EMPLOYEE_1)
		response = self.send(
			client,
			"GET",
			"/api/method/frappe.desk.form.load.getdoc",
			query={"doctype": DOCTYPE, "name": self.records[MANAGER_1]},
		)

		self.assertEqual(response.status_code, 403)
		self.assertNotIn(self.files[self.records[MANAGER_1]][1], response.get_data(as_text=True))


class TestDataImportExport(SurfaceMatrixTestCase):
	"""The Data Import screen exports records too, with its own endpoint."""

	def exported_rows(self, client) -> list[list[str]]:
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.core.doctype.data_import.data_import.download_template",
			body={
				"doctype": DOCTYPE,
				"export_fields": {DOCTYPE: ["name", "title", "salary_amount"]},
				"export_records": "all",
				"file_type": "CSV",
			},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip("﻿"))))

	def test_export_returns_the_records_of_the_list(self):
		known = set(self.records.values())
		for user, owners in EXPECTED_VISIBLE.items():
			with self.subTest(user=user):
				rows = self.exported_rows(self.login(user))
				self.assertEqual(
					{cell for row in rows[1:] for cell in row if cell in known}, self.names_of(owners)
				)

	def test_export_leaves_out_the_level_1_field(self):
		text = json.dumps(self.exported_rows(self.login(EMPLOYEE_1)))

		self.assertNotIn(SALARY_TEXT, text)


class TestLevelOneFieldOnEverySurface(SurfaceMatrixTestCase):
	"""The level 1 field stays hidden on the surfaces that `test_field_level.py` does not cover."""

	def test_list_report_does_not_return_the_field(self):
		client = self.login(EMPLOYEE_1)
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.desk.reportview.get",
			body={
				"doctype": DOCTYPE,
				"fields": json.dumps([f"`tab{DOCTYPE}`.`name`", f"`tab{DOCTYPE}`.`salary_amount`"]),
				"page_length": 500,
			},
		)

		self.assertIn(response.status_code, (200, 403))
		self.assertNotIn(SALARY_TEXT, response.get_data(as_text=True))

	def test_list_export_does_not_return_the_field(self):
		client = self.login(EMPLOYEE_1)
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.desk.reportview.export_query",
			body={
				"doctype": DOCTYPE,
				"fields": json.dumps([f"`tab{DOCTYPE}`.`name`", f"`tab{DOCTYPE}`.`salary_amount`"]),
				"file_format_type": "CSV",
				"title": DOCTYPE,
				"page_length": 500,
			},
		)

		self.assertIn(response.status_code, (200, 403))
		self.assertNotIn(SALARY_TEXT, response.get_data(as_text=True))

	def test_desk_form_load_does_not_return_the_field(self):
		client = self.login(EMPLOYEE_1)
		response = self.send(
			client,
			"GET",
			"/api/method/frappe.desk.form.load.getdoc",
			query={"doctype": DOCTYPE, "name": self.records[EMPLOYEE_1]},
		)

		self.assertEqual(response.status_code, 200)
		self.assertNotIn(SALARY_TEXT, response.get_data(as_text=True))

	def test_get_value_does_not_return_the_field(self):
		client = self.login(EMPLOYEE_1)
		response = self.send(
			client,
			"GET",
			"/api/method/frappe.client.get_value",
			query={
				"doctype": DOCTYPE,
				"fieldname": json.dumps(["name", "salary_amount"]),
				"filters": json.dumps({"name": self.records[EMPLOYEE_1]}),
			},
		)

		self.assertIn(response.status_code, (200, 403))
		self.assertNotIn(SALARY_TEXT, response.get_data(as_text=True))

	def test_role_with_the_level_reads_the_field_on_the_list_report(self):
		client = self.login(HR)
		response = self.send(
			client,
			"POST",
			"/api/method/frappe.desk.reportview.get",
			body={
				"doctype": DOCTYPE,
				"fields": json.dumps([f"`tab{DOCTYPE}`.`name`", f"`tab{DOCTYPE}`.`salary_amount`"]),
				"page_length": 500,
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn(SALARY_TEXT, response.get_data(as_text=True))


class TestAiToolLayer(SurfaceMatrixTestCase):
	"""The MCP tools of the AI layer run as the user. They give the decision of the list and the record.

	The test calls the MCP endpoint over HTTP. The access module does not import the AI module.
	"""

	def agent(self, user: str):
		client = self.login(user)
		sid = client.get_cookie("sid").value
		session = frappe.cache.hget("session", sid)
		session["data"]["csrf_token"] = frappe.generate_hash()
		frappe.cache.hset("session", sid, session)
		token_response = self.send_with_headers(
			client,
			"/api/method/platform_core.api.ai.issue_agent_token",
			{},
			{"X-Frappe-CSRF-Token": session["data"]["csrf_token"]},
		)
		self.assertEqual(token_response.status_code, 200, token_response.get_data(as_text=True))
		# The agent sends only its token. A request with a session cookie and a token is refused.
		return self.anonymous(), token_response.json["message"]["token"]

	def send_with_headers(self, client, path: str, body: dict, headers: dict):
		from frappe.tests.test_api import make_request

		kwargs = {
			"path": path,
			"method": "POST",
			"headers": {"Accept": "application/json", "Content-Type": "application/json", **headers},
			"data": json.dumps(body),
		}
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def call_tool(self, client, token: str, name: str, arguments: dict) -> dict:
		response = self.send_with_headers(
			client,
			MCP_PATH,
			{
				"jsonrpc": "2.0",
				"id": 1,
				"method": "tools/call",
				"params": {"name": name, "arguments": arguments},
			},
			{"Authorization": f"Bearer {token}"},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["result"]

	def test_list_tool_returns_the_records_of_the_list(self):
		for user, owners in EXPECTED_VISIBLE.items():
			with self.subTest(user=user):
				client, token = self.agent(user)
				result = self.call_tool(
					client,
					token,
					"plt_list_documents",
					{"doctype": DOCTYPE, "fields": ["name"], "limit": 100},
				)
				self.assertFalse(result.get("isError"), result)
				names = {row["name"] for row in result["structuredContent"]["documents"]}
				self.assertEqual(names, self.names_of(owners))

	def test_record_tool_refuses_a_record_outside_the_rule(self):
		client, token = self.agent(EMPLOYEE_1)

		result = self.call_tool(
			client, token, "plt_get_document", {"doctype": DOCTYPE, "name": self.records[MANAGER_1]}
		)

		self.assertTrue(result.get("isError"), result)
		self.assertNotIn(SALARY_TEXT, json.dumps(result))

	def test_record_tool_leaves_out_the_level_1_field(self):
		client, token = self.agent(EMPLOYEE_1)

		result = self.call_tool(
			client, token, "plt_get_document", {"doctype": DOCTYPE, "name": self.records[EMPLOYEE_1]}
		)

		self.assertFalse(result.get("isError"), result)
		self.assertNotIn(SALARY_TEXT, json.dumps(result))

	def test_list_tool_refuses_the_level_1_field(self):
		client, token = self.agent(EMPLOYEE_1)

		result = self.call_tool(
			client,
			token,
			"plt_list_documents",
			{"doctype": DOCTYPE, "fields": ["name", "salary_amount"], "limit": 100},
		)

		self.assertTrue(result.get("isError"), result)
		self.assertNotIn(SALARY_TEXT, json.dumps(result))
