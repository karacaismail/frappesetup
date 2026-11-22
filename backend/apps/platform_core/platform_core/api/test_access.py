"""Authorization tests of the access endpoints. The security gate requires these two tests for each endpoint.

The detailed behavior tests are in the `platform_core/erisim/tests/` folder.
"""

import frappe

from platform_core.erisim.tests.base import DOCTYPE, EMPLOYEE_1, EMPLOYEE_2, ROLE_EMPLOYEE, ErisimTestCase

FIELD_BODY = {"doctype": DOCTYPE, "fieldname": "salary_amount", "permlevel": 0}
LEVEL_BODY = {"doctype": DOCTYPE, "role": ROLE_EMPLOYEE, "permlevel": 1, "read": True, "write": True}


class TestAccessEndpoints(ErisimTestCase):
	def explain(self, client, name: str, **query):
		return self.api(
			client, "GET", "explain_permission", query={"doctype": DOCTYPE, "name": name, **query}
		)

	def test_explain_permission_guest_denied(self):
		response = self.explain(self.anonymous(), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_explain_permission_foreign_data_denied(self):
		"""An employee cannot ask about the permission of someone else. On the record of someone else a single denial reason is returned."""
		client = self.login(EMPLOYEE_1)

		other_user = self.explain(client, self.records[EMPLOYEE_1], user=EMPLOYEE_2)
		other_record = self.explain(client, self.records[EMPLOYEE_2])
		rule_doctype = self.api(
			client, "GET", "explain_permission", query={"doctype": "Access Rule", "name": "AR-00001"}
		)

		self.assertEqual(other_user.status_code, 403, other_user.get_data(as_text=True))
		self.assertEqual(other_record.status_code, 200, other_record.get_data(as_text=True))
		self.assertFalse(other_record.json["message"]["allowed"])
		self.assertEqual(other_record.json["message"]["reason"], "not_permitted_or_missing")
		self.assertEqual(other_record.json["message"]["rules"], [])
		self.assertEqual(rule_doctype.status_code, 403, rule_doctype.get_data(as_text=True))

	def test_get_access_summary_guest_denied(self):
		response = self.api(self.anonymous(), "GET", "get_access_summary", query={"doctype": DOCTYPE})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_get_access_summary_foreign_data_denied(self):
		"""The employee has no read permission on the “Access Rule” document type."""
		response = self.api(
			self.login(EMPLOYEE_1), "GET", "get_access_summary", query={"doctype": "Access Rule"}
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_set_field_level_guest_denied(self):
		response = self.api(self.anonymous(), "POST", "set_field_level", body=FIELD_BODY)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("salary_amount").permlevel, 1)

	def test_set_field_level_foreign_data_denied(self):
		response = self.api(self.login(EMPLOYEE_1), "POST", "set_field_level", body=FIELD_BODY)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("salary_amount").permlevel, 1)

	def test_set_level_access_guest_denied(self):
		response = self.api(self.anonymous(), "POST", "set_level_access", body=LEVEL_BODY)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))

	def test_set_level_access_foreign_data_denied(self):
		response = self.api(self.login(EMPLOYEE_1), "POST", "set_level_access", body=LEVEL_BODY)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))
