import json

import frappe

from platform_core.kabuk.http_fixture import DOCTYPE, PRIVILEGED, READER, ShellHTTPFixture


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
		self.assertIn(status, (400, 403, 405))

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

		if not frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": "custom_note"}):
			create_custom_field(
				DOCTYPE,
				{
					"fieldname": "custom_note",
					"fieldtype": "Data",
					"label": "Custom note",
					"description": "Site custom note.",
				},
			)
		make_property_setter(DOCTYPE, "title", "label", "Site title", "Data")
		frappe.db.commit()
		status, _, body = self.metadata(self.reader_sid)
		self.assertEqual(status, 200)
		fields = {f["fieldname"]: f for f in json.loads(body)["message"]["schema"]["fields"]}
		self.assertIn("custom_note", fields)
		self.assertEqual(fields["title"]["label"], "Site title")
