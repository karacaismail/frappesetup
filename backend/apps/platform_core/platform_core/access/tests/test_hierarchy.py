"""Hierarchy: a manager sees their team in the `reports_to` chain (G-60, G-104)."""

import frappe

from platform_core.access.tests.base import (
	EMPLOYEE_1,
	EMPLOYEE_2,
	EMPLOYEE_3,
	EMPLOYEE_4,
	MANAGER_1,
	MANAGER_2,
	ErisimTestCase,
	employee_of,
)


class TestHierarchy(ErisimTestCase):
	def test_manager_lists_own_and_team_records(self):
		client = self.login(MANAGER_1)

		expected = self.names_of([MANAGER_1, EMPLOYEE_1, EMPLOYEE_2, EMPLOYEE_4])
		self.assertEqual(self.listed_names(client), expected)

	def test_manager_sees_indirect_report(self):
		"""calisan4 reports to calisan1. calisan1 reports to yonetici1."""
		client = self.login(MANAGER_1)

		self.assertEqual(self.rest_get(client, self.records[EMPLOYEE_4]).status_code, 200)

	def test_manager_cannot_read_another_teams_record(self):
		client = self.login(MANAGER_1)

		response = self.rest_get(client, self.records[EMPLOYEE_3])

		self.assertEqual(response.status_code, 403)

	def test_manager_cannot_read_peer_managers_record(self):
		client = self.login(MANAGER_1)

		self.assertEqual(self.rest_get(client, self.records[MANAGER_2]).status_code, 403)

	def test_team_rule_is_read_only_for_manager(self):
		"""The team rule carries only `allow_read`. A manager cannot change the record of their team."""
		client = self.login(MANAGER_1)
		target = self.records[EMPLOYEE_2]

		response = self.rest_put(client, target, {"title": "Yonetici degistirdi"})

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.stored(target, "title"), f"Talep {EMPLOYEE_2}")

	def test_employee_with_reports_but_without_manager_role_sees_only_own(self):
		"""calisan4 reports to calisan1 but calisan1 does not have the manager role."""
		client = self.login(EMPLOYEE_1)

		self.assertEqual(self.listed_names(client), {self.records[EMPLOYEE_1]})

	def test_reporting_change_takes_effect_on_next_request(self):
		"""When calisan3 is made to report to yonetici1, yonetici1 sees the record in the next request."""
		client = self.login(MANAGER_1)
		target = self.records[EMPLOYEE_3]
		self.assertEqual(self.rest_get(client, target).status_code, 403)
		self.addCleanup(self.set_manager, EMPLOYEE_3, MANAGER_2)

		self.set_manager(EMPLOYEE_3, MANAGER_1)

		self.assertEqual(self.rest_get(client, target).status_code, 200)
		self.assertIn(target, self.listed_names(client))

	def set_manager(self, user: str, manager: str) -> None:
		frappe.set_user("Administrator")
		employee = frappe.get_doc("Employee", employee_of(user))
		employee.reports_to = employee_of(manager)
		employee.save()
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
