import json
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import quote, urlencode

import frappe
from werkzeug.wrappers import Request

from platform_core.kabuk.metadata import get_doctype
from platform_core.kabuk.serialization import digest
from platform_core.tests.shell_http_fixture import (
	CHILD_DOCTYPE,
	DESK,
	DOCTYPE,
	PRIVILEGED,
	PROTECTED_DOCTYPE,
	READER,
	ShellHTTPFixture,
)
from platform_core.tests.test_shell_contract import SCHEMA_FILE, matches


class TestMetadataHTTP(ShellHTTPFixture):
	def test_get_doctype_guest_denied(self):
		status, headers, _ = self.metadata(self.privileged_sid)
		self.assertEqual(status, 200)
		status, _, _ = self.metadata(None, {"If-None-Match": headers["ETag"]})
		self.assertEqual(status, 403)

	def test_get_doctype_foreign_data_denied(self):
		status, headers, _ = self.metadata(self.privileged_sid)
		self.assertEqual(status, 200)
		status, _, body = self.metadata(self.reader_sid, {"If-None-Match": headers["ETag"]})
		self.assertEqual(status, 200)
		fields = json.loads(body)["message"]["schema"]["fields"]
		self.assertNotIn("private_note", {field["fieldname"] for field in fields})

	def test_website_and_desk_users_get_different_fields_and_etags(self):
		low_status, low_headers, low_body = self.metadata(self.reader_sid)
		high_status, high_headers, high_body = self.metadata(self.desk_sid)
		self.assertEqual((low_status, high_status), (200, 200))
		low = json.loads(low_body)["message"]
		high = json.loads(high_body)["message"]
		self.assertNotIn("private_note", [f["fieldname"] for f in low["schema"]["fields"]])
		self.assertNotIn("private_section", [f["fieldname"] for f in low["schema"]["fields"]])
		self.assertIn("private_note", [f["fieldname"] for f in high["schema"]["fields"]])
		self.assertIn("private_section", [f["fieldname"] for f in high["schema"]["fields"]])
		self.assertNotEqual(low_headers["ETag"], high_headers["ETag"])
		for payload in (low, high):
			self.assertEqual(
				payload["meta_hash"],
				digest(
					{
						"schema": payload["schema"],
						"child_tables": payload["child_tables"],
					}
				),
			)
		self.assertNotEqual(low["meta_hash"], high["meta_hash"])
		self.assertEqual(low_headers["Cache-Control"], "private, no-store")

	def test_conditional_get_has_empty_304_body(self):
		status, headers, _ = self.metadata(self.reader_sid)
		self.assertEqual(status, 200)
		status, new_headers, body = self.metadata(self.reader_sid, {"If-None-Match": "W/" + headers["ETag"]})
		self.assertEqual(status, 304)
		self.assertEqual(body, b"")
		self.assertEqual(new_headers["ETag"], headers["ETag"])
		self.assertEqual(new_headers["Cache-Control"], "private, no-store")

	def test_post_is_rejected(self):
		status, _, _ = self.request(
			"/api/method/platform_core.api.meta.get_doctype",
			self.reader_sid,
			method="POST",
			data={"doctype": DOCTYPE},
		)
		self.assertEqual(status, 403)

	def test_role_revocation_invalidates_cached_schema(self):
		status, headers, _ = self.metadata(self.desk_sid)
		self.assertEqual(status, 200)
		frappe.set_user("Administrator")
		doc = frappe.get_doc("User", DESK)
		doc.set("roles", [{"role": "Shell Test Desk"}, {"role": "Kabuk Test Reader"}])
		doc.save()
		frappe.db.commit()
		try:
			status, new_headers, body = self.metadata(self.desk_sid, {"If-None-Match": headers["ETag"]})
			self.assertEqual(status, 200)
			self.assertNotEqual(new_headers["ETag"], headers["ETag"])
			self.assertNotIn(
				"private_note", [f["fieldname"] for f in json.loads(body)["message"]["schema"]["fields"]]
			)
		finally:
			doc = frappe.get_doc("User", DESK)
			doc.set(
				"roles",
				[
					{"role": "Shell Test Desk"},
					{"role": "Kabuk Test Reader"},
					{"role": "Kabuk Test Privileged"},
				],
			)
			doc.save()
			frappe.db.commit()

	def test_custom_field_and_property_setter_are_effective(self):
		frappe.set_user("Administrator")
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		fieldname = "review_note"
		existing_field = frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": fieldname})
		custom = (
			frappe.get_doc("Custom Field", existing_field)
			if existing_field
			else create_custom_field(
				DOCTYPE,
				{
					"fieldname": fieldname,
					"fieldtype": "Data",
					"label": "Review note",
					"description": "A site-specific note.",
				},
			)
		)
		self.addCleanup(self.delete_fixture, custom)
		existing_setter = frappe.db.exists(
			"Property Setter", {"doc_type": DOCTYPE, "field_name": fieldname, "property": "label"}
		)
		if existing_setter:
			setter = frappe.get_doc("Property Setter", existing_setter)
			setter.value = "Site note"
			setter.save()
		else:
			setter = make_property_setter(DOCTYPE, fieldname, "label", "Site note", "Data")
		self.addCleanup(self.delete_fixture, setter)
		frappe.db.commit()
		status, _, body = self.metadata(self.reader_sid)
		self.assertEqual(status, 200)
		fields = {field["fieldname"]: field for field in json.loads(body)["message"]["schema"]["fields"]}
		self.assertEqual(fields[fieldname]["label"], "Site note")

	def delete_fixture(self, doc):
		frappe.delete_doc(doc.doctype, doc.name)
		frappe.db.commit()

	def test_shared_record_includes_readable_structural_fields(self):
		from frappe import share

		doc = frappe.get_doc({"doctype": PROTECTED_DOCTYPE, "title": "Shared review record"}).insert()
		self.addCleanup(self.delete_fixture, doc)
		share.add(PROTECTED_DOCTYPE, doc.name, user=READER, read=1)
		self.addCleanup(share.remove, PROTECTED_DOCTYPE, doc.name, READER)
		frappe.db.commit()
		status, _, body = self.metadata(self.reader_sid, doctype=PROTECTED_DOCTYPE)
		self.assertEqual(status, 200)
		payload = json.loads(body)["message"]
		self.assertIn("entries", {field["fieldname"] for field in payload["schema"]["fields"]})
		child = payload["child_tables"][CHILD_DOCTYPE]
		self.assertEqual({field["fieldname"] for field in child["fields"]}, {"entry"})

	def test_protected_and_missing_doctypes_are_indistinguishable(self):
		bodies = []
		for doctype in (
			PROTECTED_DOCTYPE,
			"Nonexistent Shell Test DocType",
			"Missing O'Reilly Record",
			CHILD_DOCTYPE,
		):
			with self.subTest(doctype=doctype):
				status, _, body = self.metadata(self.reader_sid, doctype=doctype)
				self.assertEqual(status, 403)
				self.assertEqual(json.loads(body)["exc_type"], "PermissionError")
				bodies.append(json.loads(body))
		self.assertTrue(all(body == bodies[0] for body in bodies[1:]))

	def test_doctype_returns_the_canonical_name(self):
		status, _, body = self.metadata(self.reader_sid, doctype=DOCTYPE.lower())
		self.assertEqual(status, 200)
		self.assertEqual(json.loads(body)["message"]["schema"]["name"], DOCTYPE)

	def test_invalid_doctype_names(self):
		for doctype in ("", "x" * 141):
			with self.subTest(doctype=doctype):
				status, _, _ = self.metadata(self.reader_sid, doctype=doctype)
				self.assertEqual(status, 417)

	def test_child_fields_inherit_parent_permission_levels(self):
		for sid, can_read_private in ((self.reader_sid, False), (self.desk_sid, True)):
			status, _, body = self.metadata(sid)
			self.assertEqual(status, 200)
			child = json.loads(body)["message"]["child_tables"][CHILD_DOCTYPE]
			names = {field["fieldname"] for field in child["fields"]}
			self.assertIn("entry", names)
			self.assertEqual("private_entry" in names, can_read_private)

	def test_direct_module_call_enforces_permissions(self):
		frappe.set_user(READER)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_doctype(PROTECTED_DOCTYPE, READER)
			with self.assertRaises(frappe.PermissionError):
				get_doctype(DOCTYPE, PRIVILEGED)
		finally:
			frappe.set_user("Administrator")

	def test_website_user_cannot_read_native_doctype_metadata(self):
		path = f"/api/v2/doctype/{quote(DOCTYPE)}/meta"
		status, _, body = self.request(path, self.reader_sid)
		self.assertEqual(status, 403)
		self.assertNotIn("data", json.loads(body))
		status, _, _ = self.metadata(self.reader_sid)
		self.assertEqual(status, 200)

	def test_website_user_cannot_open_desk(self):
		status, _, _ = self.request("/desk", self.reader_sid)
		self.assertEqual(status, 403)

	def test_website_user_cannot_read_native_form_rpc_or_alias(self):
		method = "frappe.desk.form.load.getdoctype"
		alias = "frappe.tests.test_form_load.getdoctype"
		query = urlencode({"doctype": PROTECTED_DOCTYPE})
		paths = [
			f"/api/method/{method}?{query}",
			f"/api/v1/method/{method}?{query}",
			f"/api/v2/method/{method}?{query}",
			"/?" + urlencode({"cmd": method, "doctype": PROTECTED_DOCTYPE}),
			f"/api/method/{alias}?{query}",
			f"/api/v2/method/{alias}?{query}",
			"/?" + urlencode({"cmd": alias, "doctype": PROTECTED_DOCTYPE}),
		]
		for path in paths:
			with self.subTest(path=path):
				status, _, body = self.request(path, self.reader_sid)
				self.assertEqual(status, 403)
				self.assertNotIn("data", json.loads(body))
				self.assertNotIn("message", json.loads(body))

	def test_standard_doctype_rpc_methods_are_denied_only_for_website_users(self):
		methods = (
			"frappe.custom.doctype.custom_field.custom_field.get_fields_label",
			"frappe.desk.form.linked_with.get_linked_doctypes",
			"frappe.desk.doctype.list_view_settings.list_view_settings.get_default_listview_fields",
		)
		for method in methods:
			for prefix in ("/api/method/", "/api/v1/method/", "/api/v2/method/"):
				with self.subTest(method=method, prefix=prefix):
					path = f"{prefix}{method}?doctype=ToDo"
					self.assertEqual(self.request(path, self.reader_sid)[0], 403)
					self.assertEqual(self.request(path, self.desk_sid)[0], 200)
		path = "/api/method/frappe.desk.search.search_widget?doctype=ToDo&txt="
		self.assertEqual(self.request(path, self.reader_sid)[0], 403)

	def test_guest_unresolved_rpc_returns_validation_error(self):
		before = frappe.db.count("Error Log")
		for path in ("/api/method/xyz", "/?cmd=xyz"):
			with self.subTest(path=path):
				status, _, body = self.request(path)
				self.assertEqual(status, 417)
				self.assertEqual(json.loads(body)["exc_type"], "ValidationError")
		self.assertEqual(frappe.db.count("Error Log"), before)

	def test_validate_mobile_policy_guest_denied(self):
		path = "/api/method/platform_core.api.meta.validate_mobile_policy"
		self.assertEqual(self.request(path)[0], 403)

	def test_validate_mobile_policy_foreign_data_denied(self):
		path = "/api/method/platform_core.api.meta.validate_mobile_policy"
		self.assertEqual(self.request(path, self.reader_sid)[0], 403)
		self.assertEqual(self.request(path, self.desk_sid)[0], 403)

	def test_system_manager_can_validate_mobile_policy(self):
		path = "/api/method/platform_core.api.meta.validate_mobile_policy"
		request = Request.from_values(path=path)
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "response_headers", {}, create=True),
			patch.object(frappe.local, "form_dict", frappe._dict(), create=True),
		):
			self.assertEqual(
				frappe.get_attr("platform_core.api.meta.validate_mobile_policy")(),
				{"valid": True, "errors": []},
			)

	def test_website_user_can_call_allowlisted_identity_method(self):
		method = "frappe.auth.get_logged_user"
		for path in (
			f"/api/method/{method}",
			f"/api/v1/method/{method}",
			f"/api/v2/method/{method}",
			"/?cmd=" + method,
		):
			with self.subTest(path=path):
				status, _, body = self.request(path, self.reader_sid)
				self.assertEqual(status, 200)
				response = json.loads(body)
				self.assertEqual(response.get("message", response.get("data")), READER)

	def test_catalog_marks_unapproved_field_types(self):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		field = create_custom_field(
			DOCTYPE,
			{
				"fieldname": "unsupported_html",
				"fieldtype": "HTML",
				"label": "Unapproved field",
				"options": "<script>example()</script>",
			},
		)
		self.addCleanup(self.delete_fixture, field)
		frappe.db.commit()
		status, _, body = self.metadata(self.reader_sid)
		self.assertEqual(status, 200)
		payload = json.loads(body)["message"]
		self.assertEqual(payload["catalog_version"], 2)
		fields = {field["fieldname"]: field for field in payload["schema"]["fields"]}
		self.assertEqual(fields["title"]["component"], "input")
		self.assertEqual(fields["test_entries"]["component"], "table")
		self.assertIsNone(fields["unsupported_html"]["component"])
		self.assertNotIn("options", fields["unsupported_html"])

	@contextmanager
	def mobile_context(self, *, omit=None):
		identity = {
			"account": PRIVILEGED,
			"scope": "mobile",
			"site": frappe.local.site,
			"installation": "test-installation",
			"sid": "test-identity-session",
		}
		if omit:
			del identity[omit]
		request = Request.from_values(path="/api/method/platform_core.api.mobile.get_metadata")
		with (
			patch.object(frappe.local, "mobile_identity", identity, create=True),
			patch.object(frappe.local, "request", request, create=True),
		):
			yield

	def test_mobile_surface_requires_verified_route_and_omits_restricted_fields(self):
		path = "/api/method/platform_core.api.meta.get_doctype?" + urlencode(
			{"doctype": DOCTYPE, "surface": "mobile"}
		)
		self.assertEqual(self.request(path, self.privileged_sid)[0], 403)
		frappe.set_user(PRIVILEGED)
		try:
			web = get_doctype(DOCTYPE, PRIVILEGED)
			self.assertFalse(web["mobile_cache_allowed"])
			self.assertNotIn("private_note", {field["fieldname"] for field in web["schema"]["fields"]})
			with patch.dict(frappe.conf, {"shell_mobile_doctypes": [DOCTYPE, CHILD_DOCTYPE]}):
				with self.assertRaises(frappe.PermissionError):
					get_doctype(DOCTYPE, PRIVILEGED, surface="mobile")
				with self.mobile_context():
					payload = get_doctype(DOCTYPE, PRIVILEGED, surface="web")
				self.assertTrue(payload["mobile_cache_allowed"])
				components = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
				self.assertTrue(matches(payload, components["Meta"], components))
				self.assertEqual(payload["schema"]["sensitivity"], "standard")
				self.assertNotIn(
					"private_note", {field["fieldname"] for field in payload["schema"]["fields"]}
				)
				self.assertEqual(
					{field["fieldname"] for field in payload["child_tables"][CHILD_DOCTYPE]["fields"]},
					{"entry"},
				)
		finally:
			frappe.set_user("Administrator")

	def test_trusted_mobile_denies_unknown_doctypes_in_either_list(self):
		frappe.set_user(PRIVILEGED)
		try:
			for key in ("shell_mobile_doctypes", "shell_restricted_doctypes"):
				config = {"shell_mobile_doctypes": [DOCTYPE], "shell_restricted_doctypes": []}
				config[key].append("Missing Shell Policy DocType")
				with self.subTest(key=key), patch.dict(frappe.conf, config), self.mobile_context():
					with self.assertRaises(frappe.PermissionError):
						get_doctype(DOCTYPE, PRIVILEGED, surface="mobile")
		finally:
			frappe.set_user("Administrator")

	def test_masked_and_configured_fields_obey_surface_policy(self):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		field = create_custom_field(
			DOCTYPE, {"fieldname": "mask_test", "fieldtype": "Data", "label": "Masked test field", "mask": 1}
		)
		self.addCleanup(self.delete_fixture, field)
		frappe.db.commit()
		with patch.dict(frappe.conf, {"shell_restricted_fields": {DOCTYPE: ["title"]}}):
			frappe.set_user(DESK)
			try:
				fields = {
					entry["fieldname"]: entry for entry in get_doctype(DOCTYPE, DESK)["schema"]["fields"]
				}
				self.assertEqual(fields["mask_test"]["sensitivity"], "restricted")
				self.assertTrue(fields["mask_test"]["read_only"])
				self.assertEqual(fields["title"]["sensitivity"], "restricted")
			finally:
				frappe.set_user("Administrator")
			fields = {
				entry["fieldname"]: entry
				for entry in get_doctype(DOCTYPE, "Administrator")["schema"]["fields"]
			}
			self.assertEqual(fields["mask_test"]["sensitivity"], "restricted")
			self.assertFalse(fields["mask_test"]["read_only"])

			frappe.set_user(PRIVILEGED)
			try:
				fields = {
					entry["fieldname"] for entry in get_doctype(DOCTYPE, PRIVILEGED)["schema"]["fields"]
				}
				self.assertNotIn("mask_test", fields)
				self.assertNotIn("title", fields)
			finally:
				frappe.set_user("Administrator")

	def test_http_metadata_translates_display_text_and_preserves_select_values(self):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_field

		field = create_custom_field(
			DOCTYPE,
			{
				"fieldname": "locale_test",
				"fieldtype": "Select",
				"label": "User",
				"description": "User",
				"options": "User",
			},
		)
		self.addCleanup(self.delete_fixture, field)
		frappe.db.commit()
		path = "/api/method/platform_core.api.meta.get_doctype?" + urlencode(
			{"doctype": DOCTYPE, "_lang": "tr"}
		)
		status, _, body = self.request(path, self.reader_sid)
		self.assertEqual(status, 200)
		payload = json.loads(body)["message"]
		value = next(field for field in payload["schema"]["fields"] if field["fieldname"] == "locale_test")
		self.assertEqual(value["label"], "Kullan\u0131c\u0131")
		self.assertEqual(value["description"], "Kullan\u0131c\u0131")
		self.assertEqual(value["choices"], [{"value": "User", "label": "Kullan\u0131c\u0131"}])

	def test_verified_mobile_identity_cannot_select_web_metadata(self):
		frappe.set_user(PRIVILEGED)
		try:
			with patch.dict(frappe.conf, {"shell_mobile_doctypes": [DOCTYPE]}), self.mobile_context():
				payload = get_doctype(DOCTYPE, PRIVILEGED, surface="web")
			self.assertTrue(payload["mobile_cache_allowed"])
			self.assertNotIn("private_note", {field["fieldname"] for field in payload["schema"]["fields"]})
		finally:
			frappe.set_user("Administrator")

	def test_mobile_allowlist_typo_does_not_disable_web_metadata(self):
		frappe.set_user(PRIVILEGED)
		try:
			with patch.dict(frappe.conf, {"shell_mobile_doctypes": ["Unknown Shell Test DocType"]}):
				payload = get_doctype(DOCTYPE, PRIVILEGED)
			self.assertFalse(payload["mobile_cache_allowed"])
		finally:
			frappe.set_user("Administrator")

	def test_mobile_identity_requires_installation_and_sid(self):
		frappe.set_user(PRIVILEGED)
		try:
			for field in ("installation", "sid"):
				with (
					self.subTest(field=field),
					patch.dict(frappe.conf, {"shell_mobile_doctypes": [DOCTYPE]}),
					self.mobile_context(omit=field),
					self.assertRaises(frappe.PermissionError),
				):
					get_doctype(DOCTYPE, PRIVILEGED, surface="mobile")
		finally:
			frappe.set_user("Administrator")
