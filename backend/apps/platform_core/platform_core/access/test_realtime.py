"""The realtime room check on governed document types (G-121).

The tests call the engine's endpoint by its own address. `tests/test_surface_matrix.py` calls
Frappe's address, which `hooks.py` points to the same function.
"""

from platform_core.access.tests.base import (
	DOCTYPE,
	EMPLOYEE_1,
	EXPECTED_VISIBLE,
	FREE_DOCTYPE,
	HR,
	MANAGER_1,
	MANAGER_2,
	AccessRuleTestCase,
)

ENDPOINT = "/api/method/platform_core.access.realtime.has_permission"


class TestRealtimeRoomCheck(AccessRuleTestCase):
	def room_answer(self, client, name: str, doctype: str = DOCTYPE):
		return self.send(client, "GET", ENDPOINT, query={"doctype": doctype, "name": name, "ptype": "read"})

	def test_has_permission_guest_denied(self):
		for name in (self.records[EMPLOYEE_1], ""):
			with self.subTest(name=name):
				self.assertEqual(self.room_answer(self.anonymous(), name).status_code, 403)

	def test_has_permission_foreign_data_denied(self):
		client = self.login(EMPLOYEE_1)

		response = self.room_answer(client, self.records[MANAGER_1])

		self.assertEqual(response.status_code, 403)

	def test_record_room_follows_the_record_decision(self):
		for user, owners in EXPECTED_VISIBLE.items():
			client = self.login(user)
			expected = self.names_of(owners)
			for name in self.records.values():
				with self.subTest(user=user, record=self.owner_of[name]):
					status = self.room_answer(client, name).status_code
					self.assertEqual(status, 200 if name in expected else 403)

	def test_list_room_is_closed_to_a_narrowed_user(self):
		for user in (EMPLOYEE_1, MANAGER_1, MANAGER_2):
			with self.subTest(user=user):
				self.assertEqual(self.room_answer(self.login(user), "").status_code, 403)

	def test_list_room_is_open_to_a_user_who_sees_every_record(self):
		response = self.room_answer(self.login(HR), "")

		self.assertEqual(response.status_code, 200)
		self.assertIs(response.json["message"], True)

	def test_list_room_of_an_ungoverned_type_is_left_to_frappe(self):
		response = self.room_answer(self.login(EMPLOYEE_1), "", doctype=FREE_DOCTYPE)

		self.assertEqual(response.status_code, 200)
