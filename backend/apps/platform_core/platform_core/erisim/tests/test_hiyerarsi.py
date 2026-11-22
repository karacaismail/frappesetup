"""Hiyerarşi: yönetici `reports_to` zincirindeki ekibini görür (G-60, G-104)."""

import frappe

from platform_core.erisim.tests.base import (
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
		"""calisan4, calisan1'e bağlıdır. calisan1 de yonetici1'e bağlıdır."""
		client = self.login(MANAGER_1)

		self.assertEqual(self.rest_get(client, self.records[EMPLOYEE_4]).status_code, 200)

	def test_manager_cannot_read_another_teams_record(self):
		client = self.login(MANAGER_1)

		response = self.rest_get(client, self.records[EMPLOYEE_3])

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_manager_cannot_read_peer_managers_record(self):
		client = self.login(MANAGER_1)

		self.assertEqual(self.rest_get(client, self.records[MANAGER_2]).status_code, 403)

	def test_team_rule_is_read_only_for_manager(self):
		"""Ekip kuralı yalnız `allow_read` taşır. Yönetici ekibinin kaydını değiştiremez."""
		client = self.login(MANAGER_1)
		target = self.records[EMPLOYEE_2]

		response = self.rest_put(client, target, {"title": "Yonetici degistirdi"})

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
		self.assertEqual(self.stored(target, "title"), f"Talep {EMPLOYEE_2}")

	def test_employee_with_reports_but_without_manager_role_sees_only_own(self):
		"""calisan1'e calisan4 bağlıdır ama calisan1 yönetici rolü taşımaz."""
		client = self.login(EMPLOYEE_1)

		self.assertEqual(self.listed_names(client), {self.records[EMPLOYEE_1]})

	def test_reporting_change_takes_effect_on_next_request(self):
		"""calisan3 yonetici1'e bağlanınca yonetici1 kaydı sonraki istekte görür."""
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
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır
