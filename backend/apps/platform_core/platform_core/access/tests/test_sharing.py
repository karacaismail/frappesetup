"""Share: a shared record goes past the rule and is visible on both surfaces (G-12; decision note, section 10)."""

import frappe
import frappe.share

from platform_core.access.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	EMPLOYEE_3,
	ErisimTestCase,
)

SHARE = "/api/method/frappe.share.add"


class TestSharing(ErisimTestCase):
	def share_with_employee_1(self, name: str, **rights) -> None:
		frappe.set_user("Administrator")
		frappe.share.add_docshare(DOCTYPE, name, EMPLOYEE_1, read=1, **rights)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		self.addCleanup(self.unshare, name)

	def unshare(self, name: str) -> None:
		frappe.set_user("Administrator")
		frappe.db.delete("DocShare", {"share_doctype": DOCTYPE, "share_name": name})
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_shared_record_is_visible_on_list_and_document(self):
		shared = self.records[EMPLOYEE_2]
		client = self.login(EMPLOYEE_1)
		self.assertEqual(self.rest_get(client, shared).status_code, 403)

		self.share_with_employee_1(shared)

		self.assertEqual(self.listed_names(client), {self.records[EMPLOYEE_1], shared})
		self.assertEqual(self.readable_names(client), {self.records[EMPLOYEE_1], shared})

	def test_read_share_does_not_allow_write(self):
		shared = self.records[EMPLOYEE_2]
		self.share_with_employee_1(shared)
		client = self.login(EMPLOYEE_1)

		response = self.rest_put(client, shared, {"title": "Paylasimla degisti"})

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.stored(shared, "title"), f"Talep {EMPLOYEE_2}")

	def test_shared_record_cannot_be_deleted(self):
		"""Delete cannot be shared. The denial stays because the rule does not cover delete."""
		shared = self.records[EMPLOYEE_2]
		self.share_with_employee_1(shared, write=1)
		client = self.login(EMPLOYEE_1)

		response = self.rest_delete(client, shared)

		self.assertEqual(response.status_code, 403)
		self.assertTrue(frappe.db.exists(DOCTYPE, shared))

	def test_user_outside_the_rule_cannot_share_a_record(self):
		"""The `share` operation goes through the record hook. An employee cannot share a record they cannot see."""
		target = self.records[EMPLOYEE_3]
		client = self.login(EMPLOYEE_1)

		response = self.send(
			client, "POST", SHARE, body={"doctype": DOCTYPE, "name": target, "user": EMPLOYEE_2, "read": 1}
		)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": DOCTYPE, "share_name": target}))

	def test_explain_names_share_as_the_reason(self):
		shared = self.records[EMPLOYEE_2]
		self.share_with_employee_1(shared)
		admin = self.login(ADMIN)

		response = self.api(
			admin, "GET", "explain_permission", query={"doctype": DOCTYPE, "name": shared, "user": EMPLOYEE_1}
		)

		self.assertEqual(response.status_code, 200)
		message = response.json["message"]
		self.assertTrue(message["allowed"])
		self.assertEqual(message["reason"], "allowed_by_share")
		self.assertEqual(message["layers"], {"role": True, "access_rule": False, "share": True})
