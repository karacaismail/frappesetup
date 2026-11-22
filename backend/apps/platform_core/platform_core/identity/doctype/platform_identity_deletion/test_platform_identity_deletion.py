"""`Platform Identity Deletion` record tests (M-5, docs/sozlesmeler.md section 7, rule 2)."""

import frappe
from frappe.tests import IntegrationTestCase

DELETION = "Platform Identity Deletion"
DIGEST = "a" * 64


class TestPlatformIdentityDeletion(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete(DELETION, {"name": DIGEST})

	def tearDown(self):
		frappe.db.delete(DELETION, {"name": DIGEST})
		super().tearDown()

	def new(self):
		return frappe.get_doc(
			{"doctype": DELETION, "identity_hash": DIGEST, "state": "Disabled", "user": "x"}
		)

	def test_digest_is_the_name_and_unique(self):
		self.assertEqual(self.new().insert().name, DIGEST)
		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			self.new().insert()

	def test_nobody_creates_or_edits_it_from_the_desk(self):
		for permission in frappe.get_meta(DELETION).permissions:
			self.assertFalse(permission.create or permission.write or permission.delete, permission.role)

	def test_it_keeps_no_raw_identity_field(self):
		fields = {df.fieldname for df in frappe.get_meta(DELETION).fields}
		self.assertEqual(fields, {"identity_hash", "state", "user", "deleted_at"})
