"""Okuma araçları: yetki eşitliği, izin seviyesi ve gizli alanlar (G-85)."""

import frappe

from platform_core.yapay_zeka.tests.base import DOCTYPE, MANAGER, USER_A, USER_B, YzTestCase


class TestReadTools(YzTestCase):
	def test_restricted_user_cannot_read_another_users_document(self):
		name = self.make_record(USER_A, title="A kaydi")
		client_b = self.login(USER_B)

		result = self.call_tool(client_b, "get_document", {"doctype": DOCTYPE, "name": name})

		self.assert_denied(result, "permission")
		log = self.last_log(tool="get_document", target_name=name)
		self.assertEqual(log.decision, "denied")
		self.assertEqual(log.deny_reason, "permission")
		self.assertEqual(log.user, USER_B)
		self.assertEqual(log.principal, "human_session")

	def test_list_shows_only_documents_the_user_may_read(self):
		name_a = self.make_record(USER_A)
		name_b = self.make_record(USER_B)
		client_b = self.login(USER_B)

		result = self.call_tool(client_b, "list_documents", {"doctype": DOCTYPE, "fields": ["name", "title"]})

		self.assertFalse(result["isError"], result)
		names = {row["name"] for row in result["structuredContent"]["documents"]}
		self.assertIn(name_b, names)
		self.assertNotIn(name_a, names)

	def test_owner_reads_own_document_and_call_is_logged(self):
		name = self.make_record(USER_A, title="Benim kaydim")
		client_a = self.login(USER_A)

		result = self.call_tool(client_a, "get_document", {"doctype": DOCTYPE, "name": name})

		self.assertFalse(result["isError"], result)
		self.assertEqual(result["structuredContent"]["document"]["title"], "Benim kaydim")
		log = self.last_log(tool="get_document", target_name=name)
		self.assertEqual(log.decision, "allowed")
		self.assertEqual(log.tool_class, "read")
		self.assertEqual(len(log.args_hash), 64)

	def test_higher_permlevel_field_is_not_returned(self):
		name = self.make_record(USER_A)
		frappe.db.set_value(DOCTYPE, name, "internal_note", "yalniz yonetici")
		client_a = self.login(USER_A)

		document = self.call_tool(client_a, "get_document", {"doctype": DOCTYPE, "name": name})
		listing = self.call_tool(
			client_a, "list_documents", {"doctype": DOCTYPE, "fields": ["name", "internal_note"]}
		)
		filtered = self.call_tool(
			client_a, "list_documents", {"doctype": DOCTYPE, "filters": {"internal_note": "yalniz yonetici"}}
		)

		self.assertNotIn("internal_note", document["structuredContent"]["document"])
		self.assert_denied(listing, "field_not_permitted")
		self.assert_denied(filtered, "field_not_permitted")

	def test_manager_reads_higher_permlevel_field(self):
		name = self.make_record(USER_A)
		frappe.db.set_value(DOCTYPE, name, "internal_note", "yalniz yonetici")
		manager = self.login(MANAGER)

		document = self.call_tool(manager, "get_document", {"doctype": DOCTYPE, "name": name})

		self.assertEqual(document["structuredContent"]["document"]["internal_note"], "yalniz yonetici")

	def test_password_and_secret_named_fields_are_never_returned(self):
		name = self.make_record(USER_A, vault_code="cok-gizli-deger", access_token="gizli-belirtec")
		manager = self.login(MANAGER)

		document = self.call_tool(manager, "get_document", {"doctype": DOCTYPE, "name": name})
		by_field = self.call_tool(
			manager, "list_documents", {"doctype": DOCTYPE, "fields": ["name", "vault_code"]}
		)
		by_filter = self.call_tool(
			manager, "list_documents", {"doctype": DOCTYPE, "filters": {"access_token": "gizli-belirtec"}}
		)
		by_order = self.call_tool(
			manager, "list_documents", {"doctype": DOCTYPE, "order_by": "access_token asc"}
		)

		self.assertFalse(document["isError"], document)
		payload = document["structuredContent"]["document"]
		self.assertNotIn("vault_code", payload)
		self.assertNotIn("access_token", payload)
		self.assertNotIn("cok-gizli-deger", document["content"][0]["text"])
		self.assertNotIn("gizli-belirtec", document["content"][0]["text"])
		self.assert_denied(by_field, "secret_field")
		self.assert_denied(by_filter, "secret_field")
		self.assert_denied(by_order, "secret_field")

	def test_schema_describes_fields_and_marks_secrets(self):
		client_a = self.login(USER_A)

		result = self.call_tool(client_a, "get_doctype_schema", {"doctype": DOCTYPE})

		self.assertFalse(result["isError"], result)
		schema = result["structuredContent"]
		fields = {field["fieldname"]: field for field in schema["fields"]}
		self.assertEqual(fields["title"]["description"], "Short title.")
		self.assertTrue(fields["vault_code"]["secret"])
		self.assertTrue(fields["access_token"]["secret"])
		self.assertFalse(fields["internal_note"]["readable"])
		self.assertTrue(fields["title"]["writable"])
		self.assertFalse(fields["vault_code"]["writable"])
		self.assertTrue(schema["permissions"]["read"])

	def test_doctype_without_permission_is_denied_and_logged(self):
		client_a = self.login(USER_A)

		result = self.call_tool(client_a, "list_documents", {"doctype": "Error Log"})
		search = self.call_tool(client_a, "search_doctypes", {"query": "YZ Test"})

		self.assert_denied(result, "permission")
		self.assertEqual(self.last_log(tool="list_documents", target_doctype="Error Log").decision, "denied")
		self.assertIn(DOCTYPE, search["structuredContent"]["doctypes"])
		self.assertNotIn(
			"Error Log", self.call_tool(client_a, "search_doctypes", {})["structuredContent"]["doctypes"]
		)

	def test_credential_doctype_is_blocked_even_for_manager(self):
		manager = self.login(MANAGER)

		result = self.call_tool(manager, "list_documents", {"doctype": "OAuth Bearer Token"})

		self.assert_denied(result, "blocked_doctype")

	def test_report_needs_report_permission(self):
		client_a = self.login(USER_A)
		manager = self.login(MANAGER)

		denied = self.call_tool(client_a, "run_report", {"report": "Permitted Documents For User"})
		allowed = self.call_tool(
			manager,
			"run_report",
			{"report": "Permitted Documents For User", "filters": {"user": MANAGER, "doctype": DOCTYPE}},
		)

		self.assert_denied(denied, "permission")
		self.assertFalse(allowed["isError"], allowed)
		self.assertIn("columns", allowed["structuredContent"])
		self.assertIn("rows", allowed["structuredContent"])

	def test_unknown_argument_is_rejected(self):
		client_a = self.login(USER_A)

		result = self.call_tool(client_a, "get_document", {"doctype": DOCTYPE, "name": "x", "confirm": True})

		self.assert_denied(result, "invalid_arguments")
