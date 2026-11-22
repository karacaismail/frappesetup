import json

import frappe

from platform_core.kabuk.metadata import get_doctype
from platform_core.kabuk.serialization import digest
from platform_core.tests.shell_http_fixture import (
	CHILD_DOCTYPE,
	DOCTYPE,
	PRIVILEGED,
	PROTECTED_DOCTYPE,
	READER,
	ShellHTTPFixture,
)


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

	def test_two_website_users_get_different_fields_and_etags(self):
		low_status, low_headers, low_body = self.metadata(self.reader_sid)
		high_status, high_headers, high_body = self.metadata(self.privileged_sid)
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
		status, headers, _ = self.metadata(self.privileged_sid)
		self.assertEqual(status, 200)
		frappe.set_user("Administrator")
		doc = frappe.get_doc("User", PRIVILEGED)
		doc.set("roles", [{"role": "Kabuk Test Reader"}])
		doc.save()
		frappe.db.commit()
		try:
			status, new_headers, body = self.metadata(self.privileged_sid, {"If-None-Match": headers["ETag"]})
			self.assertEqual(status, 200)
			self.assertNotEqual(new_headers["ETag"], headers["ETag"])
			self.assertNotIn(
				"private_note", [f["fieldname"] for f in json.loads(body)["message"]["schema"]["fields"]]
			)
		finally:
			doc = frappe.get_doc("User", PRIVILEGED)
			doc.set("roles", [{"role": "Kabuk Test Reader"}, {"role": "Kabuk Test Privileged"}])
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
		for doctype in (PROTECTED_DOCTYPE, "Nonexistent Shell Test DocType", CHILD_DOCTYPE):
			with self.subTest(doctype=doctype):
				status, _, body = self.metadata(self.reader_sid, doctype=doctype)
				self.assertEqual(status, 403)
				self.assertEqual(json.loads(body)["exc_type"], "PermissionError")
				bodies.append(json.loads(body))
		self.assertEqual(bodies[0], bodies[1])
		self.assertEqual(bodies[0], bodies[2])

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
		for sid, can_read_private in ((self.reader_sid, False), (self.privileged_sid, True)):
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
