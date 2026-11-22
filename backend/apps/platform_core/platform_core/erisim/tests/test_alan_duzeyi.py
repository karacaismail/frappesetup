"""Field level: a restricted field is not returned and cannot be written (G-61)."""

import frappe

from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	HR,
	MANAGER_1,
	ROLE_MANAGER,
	ErisimTestCase,
)

SALARY = 1234


class TestFieldLevel(ErisimTestCase):
	def test_restricted_field_is_not_returned_on_document(self):
		client = self.login(EMPLOYEE_1)

		response = self.rest_get(client, self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 200)
		self.assert_hidden(response.json["data"], "salary_amount")
		self.assertFalse(
			str(SALARY) in response.get_data(as_text=True), "the response carries a value it must not carry"
		)

	def test_restricted_field_is_not_returned_on_list(self):
		"""Frappe either removes a field without permission from the response or denies the request. The value is never returned."""
		client = self.login(EMPLOYEE_1)

		response = self.rest_list(client, fields=("name", "salary_amount"))

		self.assertIn(response.status_code, (200, 403))
		self.assertFalse(
			str(SALARY) in response.get_data(as_text=True), "the response carries a value it must not carry"
		)

	def test_restricted_field_cannot_be_used_as_a_filter(self):
		"""A filter must not leak the value: filtering by a field without permission returns no record."""
		client = self.login(EMPLOYEE_1)

		response = self.rest_list(client, filters={"salary_amount": SALARY})

		self.assertIn(response.status_code, (200, 403))
		if response.status_code == 200:
			self.assertEqual(response.json["data"], [])

	def test_restricted_field_cannot_be_written(self):
		client = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_1]

		self.rest_put(client, target, {"salary_amount": 999999})

		self.assertEqual(self.stored(target, "salary_amount"), SALARY)

	def test_role_with_level_access_reads_the_field(self):
		client = self.login(HR)

		response = self.rest_get(client, self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["data"]["salary_amount"], SALARY)


class TestFieldLevelEndpoints(ErisimTestCase):
	"""The `set_field_level` and `set_level_access` endpoints (contract)."""

	def reset(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Property Setter", {"doc_type": DOCTYPE, "property": "permlevel"})
		frappe.db.delete("Custom DocPerm", {"parent": DOCTYPE})
		frappe.clear_cache(doctype=DOCTYPE)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def setUp(self):
		super().setUp()
		self.addCleanup(self.reset)

	def test_admin_raises_field_level_and_field_disappears(self):
		admin = self.login(ADMIN)
		employee = self.login(EMPLOYEE_1)
		target = self.records[EMPLOYEE_1]
		self.assertEqual(self.rest_get(employee, target).json["data"]["status"], "Open")

		response = self.api(
			admin, "POST", "set_field_level", body={"doctype": DOCTYPE, "fieldname": "status", "permlevel": 1}
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.json["message"],
			{"doctype": DOCTYPE, "fieldname": "status", "permlevel": 1, "previous_permlevel": 0},
		)
		self.assert_hidden(self.rest_get(employee, target).json["data"], "status")

	def test_admin_lowers_field_level_back(self):
		admin = self.login(ADMIN)
		employee = self.login(EMPLOYEE_1)
		body = {"doctype": DOCTYPE, "fieldname": "status", "permlevel": 1}
		self.api(admin, "POST", "set_field_level", body=body)

		response = self.api(admin, "POST", "set_field_level", body={**body, "permlevel": 0})

		self.assertEqual(response.json["message"]["previous_permlevel"], 1)
		self.assertEqual(self.rest_get(employee, self.records[EMPLOYEE_1]).json["data"]["status"], "Open")

	def test_non_admin_cannot_change_field_level(self):
		employee = self.login(EMPLOYEE_1)

		response = self.api(
			employee,
			"POST",
			"set_field_level",
			body={"doctype": DOCTYPE, "fieldname": "salary_amount", "permlevel": 0},
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("salary_amount").permlevel, 1)

	def test_field_level_rejects_bad_input(self):
		admin = self.login(ADMIN)
		for body in (
			{"doctype": DOCTYPE, "fieldname": "no_such_field", "permlevel": 1},
			{"doctype": DOCTYPE, "fieldname": "owner", "permlevel": 1},
			{"doctype": DOCTYPE, "fieldname": "status", "permlevel": 10},
			{"doctype": DOCTYPE, "fieldname": "status", "permlevel": -1},
		):
			response = self.api(admin, "POST", "set_field_level", body=body)
			self.assertEqual(response.status_code, 417, body)

	def test_field_level_is_post_only(self):
		admin = self.login(ADMIN)

		response = self.api(
			admin, "GET", "set_field_level", query={"doctype": DOCTYPE, "fieldname": "status", "permlevel": 1}
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.get_meta(DOCTYPE).get_field("status").permlevel, 0)

	def test_admin_grants_and_revokes_level_access(self):
		admin = self.login(ADMIN)
		manager = self.login(MANAGER_1)
		target = self.records[MANAGER_1]
		body = {"doctype": DOCTYPE, "role": ROLE_MANAGER, "permlevel": 1, "read": True, "write": False}
		self.assert_hidden(self.rest_get(manager, target).json["data"], "salary_amount")

		granted = self.api(admin, "POST", "set_level_access", body=body)

		self.assertEqual(granted.status_code, 200)
		self.assertEqual(granted.json["message"], body)
		self.assertEqual(self.rest_get(manager, target).json["data"]["salary_amount"], SALARY)

		revoked = self.api(admin, "POST", "set_level_access", body={**body, "read": False})

		self.assertEqual(revoked.status_code, 200)
		self.assert_hidden(self.rest_get(manager, target).json["data"], "salary_amount")

	def test_level_access_keeps_other_roles_permissions(self):
		"""The first change creates a “Custom DocPerm” copy. The permission of the other roles must not be lost."""
		admin = self.login(ADMIN)
		hr = self.login(HR)

		self.api(
			admin,
			"POST",
			"set_level_access",
			body={"doctype": DOCTYPE, "role": ROLE_MANAGER, "permlevel": 1, "read": True, "write": False},
		)

		self.assertEqual(self.rest_get(hr, self.records[EMPLOYEE_1]).json["data"]["salary_amount"], SALARY)
		self.assertEqual(self.listed_names(self.login(EMPLOYEE_1)), {self.records[EMPLOYEE_1]})

	def test_level_access_rejects_level_zero_and_write_without_read(self):
		admin = self.login(ADMIN)
		base = {"doctype": DOCTYPE, "role": ROLE_MANAGER, "permlevel": 1, "read": True, "write": False}
		for body in ({**base, "permlevel": 0}, {**base, "read": False, "write": True}):
			response = self.api(admin, "POST", "set_level_access", body=body)
			self.assertEqual(response.status_code, 417, body)

	def test_level_access_unknown_role_is_not_found(self):
		admin = self.login(ADMIN)

		response = self.api(
			admin,
			"POST",
			"set_level_access",
			body={"doctype": DOCTYPE, "role": "ER Olmayan Rol", "permlevel": 1, "read": True, "write": False},
		)

		self.assertEqual(response.status_code, 404)

	def test_non_admin_cannot_grant_level_access(self):
		employee = self.login(EMPLOYEE_1)

		response = self.api(
			employee,
			"POST",
			"set_level_access",
			body={"doctype": DOCTYPE, "role": "ER Calisan", "permlevel": 1, "read": True, "write": True},
		)

		self.assertEqual(response.status_code, 403)
		self.assert_hidden(self.rest_get(employee, self.records[EMPLOYEE_1]).json["data"], "salary_amount")
