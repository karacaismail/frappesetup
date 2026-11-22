"""`Platform Identity Link` uniqueness tests (docs/sozlesmeler.md section 4, V-8)."""

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.kimlik.tests import helpers as h


# setUpClass creates the two users explicitly. No generated User records are needed.
IGNORE_TEST_RECORD_DEPENDENCIES = ["User"]


class TestPlatformIdentityLink(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		h.ensure_user(h.AYSE)
		h.ensure_user(h.MEHMET)

	def setUp(self):
		super().setUp()
		frappe.db.delete("Platform Identity Link", {"issuer": h.ISSUER})

	def new(self, subject, user):
		return frappe.get_doc(
			{"doctype": "Platform Identity Link", "issuer": h.ISSUER, "subject": subject, "user": user}
		)

	def test_issuer_subject_pair_is_unique_in_database(self):
		self.new("sub-1", h.AYSE).insert()
		with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
			self.new("sub-1", h.MEHMET).insert()

	def test_one_user_cannot_have_two_links(self):
		self.new("sub-1", h.AYSE).insert()
		with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
			self.new("sub-2", h.AYSE).insert()

	def test_fields_are_required_and_trimmed(self):
		doc = self.new("  sub-3  ", h.AYSE)
		doc.issuer = f"  {h.ISSUER}  "
		doc.insert()
		self.assertEqual((doc.issuer, doc.subject), (h.ISSUER, "sub-3"))
		with self.assertRaises(frappe.MandatoryError):
			self.new("", h.MEHMET).insert()

	def test_composite_unique_constraint_exists(self):
		# V-8: uniqueness lives in the database; the constraint name follows Frappe's add_unique rule.
		constraints = frappe.db.sql(
			"""select CONSTRAINT_NAME from information_schema.TABLE_CONSTRAINTS
			where table_name=%s and constraint_type='UNIQUE' and CONSTRAINT_NAME=%s""",
			("tabPlatform Identity Link", "unique_issuer_subject"),
		)
		self.assertTrue(constraints)
