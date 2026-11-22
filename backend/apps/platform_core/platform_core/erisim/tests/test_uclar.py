"""`explain_permission` ve `get_access_summary` uçları (sözleşme)."""

from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	FREE_DOCTYPE,
	HR,
	MANAGER_1,
	NO_RULE,
	ErisimTestCase,
)

OPERATIONS = ("read", "write", "create", "delete", "submit", "cancel")


class TestExplainPermission(ErisimTestCase):
	def explain(self, client, name: str, **query):
		return self.api(client, "GET", "explain_permission", query={"doctype": DOCTYPE, "name": name, **query})

	def test_user_gets_allowed_for_own_record(self):
		response = self.explain(self.login(EMPLOYEE_1), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertEqual(
			response.json["message"],
			{
				"doctype": DOCTYPE,
				"name": self.records[EMPLOYEE_1],
				"ptype": "read",
				"user": EMPLOYEE_1,
				"allowed": True,
				"reason": "allowed",
				"governed": True,
				"layers": {"role": True, "access_rule": True, "share": False},
				"rules": [],
			},
		)

	def test_user_gets_single_reason_for_denied_and_for_missing_record(self):
		"""Sözleşme: uç kayıt varlığını olağan kullanıcıya ele vermez."""
		client = self.login(EMPLOYEE_1)

		denied = self.explain(client, self.records[EMPLOYEE_2])
		missing = self.explain(client, "olmayan-kayit")

		for response in (denied, missing):
			self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
			self.assertFalse(response.json["message"]["allowed"])
			self.assertEqual(response.json["message"]["reason"], "not_permitted_or_missing")
			self.assertEqual(response.json["message"]["rules"], [])
		comparable = [
			{key: value for key, value in response.json["message"].items() if key != "name"}
			for response in (denied, missing)
		]
		self.assertEqual(comparable[0], comparable[1])

	def test_user_cannot_ask_about_another_user(self):
		response = self.explain(self.login(EMPLOYEE_1), self.records[EMPLOYEE_1], user=EMPLOYEE_2)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_admin_sees_which_rule_failed(self):
		response = self.explain(self.login(ADMIN), self.records[EMPLOYEE_2], user=EMPLOYEE_1)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		message = response.json["message"]
		self.assertFalse(message["allowed"])
		self.assertEqual(message["reason"], "no_matching_rule")
		self.assertEqual(message["layers"], {"role": True, "access_rule": False, "share": False})
		self.assertEqual(
			[(rule["title"], rule["applies"], rule["matches"]) for rule in message["rules"]],
			[
				("Calisan kendi kaydi", True, False),
				("Yonetici ekibi", False, False),
				("IK tum kayitlar", False, False),
			],
		)
		self.assertEqual(message["rules"][0]["name"], self.rules["Calisan kendi kaydi"])
		self.assertEqual(message["rules"][0]["scope"], "own")

	def test_admin_sees_matching_team_rule_for_manager(self):
		response = self.explain(self.login(ADMIN), self.records[EMPLOYEE_2], user=MANAGER_1)

		message = response.json["message"]
		self.assertTrue(message["allowed"])
		self.assertEqual(message["reason"], "allowed")
		self.assertEqual(
			[(rule["title"], rule["applies"], rule["matches"]) for rule in message["rules"]],
			[
				("Calisan kendi kaydi", True, False),
				("Yonetici ekibi", True, True),
				("IK tum kayitlar", False, False),
			],
		)

	def test_ptype_selects_the_rule_flag(self):
		"""Yönetici ekibinin kaydını okur ama yazamaz."""
		response = self.explain(
			self.login(ADMIN), self.records[EMPLOYEE_2], user=MANAGER_1, ptype="write"
		)

		message = response.json["message"]
		self.assertFalse(message["allowed"])
		self.assertEqual(message["ptype"], "write")
		self.assertEqual(message["reason"], "no_matching_rule")

	def test_admin_gets_not_found_for_missing_record(self):
		response = self.explain(self.login(ADMIN), "olmayan-kayit", user=EMPLOYEE_1)

		self.assertEqual(response.status_code, 404, response.get_data(as_text=True))

	def test_invalid_ptype_is_rejected(self):
		response = self.explain(self.login(EMPLOYEE_1), self.records[EMPLOYEE_1], ptype="drop")

		self.assertEqual(response.status_code, 417, response.get_data(as_text=True))

	def test_guest_is_rejected(self):
		response = self.explain(self.anonymous(), self.records[EMPLOYEE_1])

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_explain_is_get_only(self):
		response = self.api(
			self.login(EMPLOYEE_1),
			"POST",
			"explain_permission",
			body={"doctype": DOCTYPE, "name": self.records[EMPLOYEE_1]},
		)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))


class TestAccessSummary(ErisimTestCase):
	def summary(self, client, doctype: str = DOCTYPE):
		return self.api(client, "GET", "get_access_summary", query={"doctype": doctype})

	def scopes(self, response) -> dict:
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		operations = response.json["message"]["operations"]
		self.assertEqual(set(operations), set(OPERATIONS))
		return {operation: sorted(scopes) for operation, scopes in operations.items()}

	def test_manager_summary_joins_both_roles(self):
		response = self.summary(self.login(MANAGER_1))

		self.assertEqual(response.json["message"]["doctype"], DOCTYPE)
		self.assertTrue(response.json["message"]["governed"])
		self.assertEqual(
			self.scopes(response),
			{
				"read": ["own", "team"],
				"write": ["own"],
				"create": ["own"],
				"delete": [],
				"submit": [],
				"cancel": [],
			},
		)

	def test_hr_summary(self):
		self.assertEqual(
			self.scopes(self.summary(self.login(HR))),
			{
				"read": ["all"],
				"write": ["all"],
				"create": ["all"],
				"delete": ["all"],
				"submit": [],
				"cancel": [],
			},
		)

	def test_role_without_rule_gets_empty_scopes_on_governed_doctype(self):
		response = self.summary(self.login(NO_RULE))

		self.assertTrue(response.json["message"]["governed"])
		self.assertEqual(self.scopes(response), {operation: [] for operation in OPERATIONS})

	def test_ungoverned_doctype_is_reported_as_not_governed(self):
		response = self.summary(self.login(NO_RULE), FREE_DOCTYPE)

		self.assertFalse(response.json["message"]["governed"])
		self.assertEqual(self.scopes(response), {operation: [] for operation in OPERATIONS})

	def test_summary_needs_role_read_permission(self):
		response = self.summary(self.login(EMPLOYEE_1), "Access Rule")

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_unknown_doctype_is_not_found(self):
		response = self.summary(self.login(EMPLOYEE_1), "ER Olmayan Tur")

		self.assertEqual(response.status_code, 404, response.get_data(as_text=True))

	def test_guest_is_rejected(self):
		response = self.summary(self.anonymous())

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
