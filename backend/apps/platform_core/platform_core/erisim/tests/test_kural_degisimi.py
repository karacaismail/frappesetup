"""When a rule changes, the result changes in the next request (task document; decision note, section 12)."""

import frappe

from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	FREE_DOCTYPE,
	NO_RULE,
	REST,
	ROLE_NO_RULE,
	RULE_DOCTYPE,
	ErisimTestCase,
)

OWN_RULE = "Calisan kendi kaydi"


class TestRuleChange(ErisimTestCase):
	def rule_path(self, title: str) -> str:
		return f"{REST}{RULE_DOCTYPE}/{self.rules[title]}"

	def restore_own_rule(self) -> None:
		frappe.set_user("Administrator")
		rule = frappe.get_doc(RULE_DOCTYPE, self.rules[OWN_RULE])
		rule.update({"is_active": 1, "scope": "own", "match_field": "employee", "allow_read": 1})
		rule.save()
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_widening_a_rule_over_rest_takes_effect_on_next_request(self):
		admin = self.login(ADMIN)
		employee = self.login(EMPLOYEE_1)
		self.assertEqual(self.listed_names(employee), {self.records[EMPLOYEE_1]})
		self.addCleanup(self.restore_own_rule)

		response = self.send(admin, "PUT", self.rule_path(OWN_RULE), body={"scope": "all", "match_field": ""})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.listed_names(employee), set(self.records.values()))
		self.assertEqual(self.readable_names(employee), set(self.records.values()))

	def test_deactivating_a_rule_removes_access_on_next_request(self):
		admin = self.login(ADMIN)
		employee = self.login(EMPLOYEE_1)
		own = self.records[EMPLOYEE_1]
		self.assertEqual(self.rest_get(employee, own).status_code, 200)
		self.addCleanup(self.restore_own_rule)

		response = self.send(admin, "PUT", self.rule_path(OWN_RULE), body={"is_active": 0})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.rest_get(employee, own).status_code, 403)
		self.assertEqual(self.listed_names(employee), set())

	def test_dropping_read_from_a_rule_removes_read_only(self):
		admin = self.login(ADMIN)
		employee = self.login(EMPLOYEE_1)
		self.addCleanup(self.restore_own_rule)

		self.send(admin, "PUT", self.rule_path(OWN_RULE), body={"allow_read": 0})

		self.assertEqual(self.rest_get(employee, self.records[EMPLOYEE_1]).status_code, 403)

	def test_first_rule_on_a_doctype_governs_it_and_deleting_it_frees_it(self):
		name = frappe.get_doc({"doctype": FREE_DOCTYPE, "title": "Serbest"}).insert().name
		self.addCleanup(frappe.delete_doc, FREE_DOCTYPE, name, force=True)
		admin = self.login(ADMIN)
		user = self.login(NO_RULE)
		self.assertEqual(self.rest_get(user, name, FREE_DOCTYPE).status_code, 200)

		created = self.send(
			admin,
			"POST",
			REST + RULE_DOCTYPE,
			body={
				"title": "Serbest tur kurali",
				"document_type": FREE_DOCTYPE,
				"role": "ER IK",
				"scope": "all",
				"allow_read": 1,
			},
		)

		self.assertEqual(created.status_code, 200)
		rule = created.json["data"]["name"]
		self.addCleanup(self.drop_rule, rule)
		self.assertEqual(self.rest_get(user, name, FREE_DOCTYPE).status_code, 403)

		deleted = self.send(admin, "DELETE", f"{REST}{RULE_DOCTYPE}/{rule}")

		self.assertIn(deleted.status_code, (200, 202))
		self.assertEqual(self.rest_get(user, name, FREE_DOCTYPE).status_code, 200)

	def drop_rule(self, rule: str) -> None:
		frappe.set_user("Administrator")
		if frappe.db.exists(RULE_DOCTYPE, rule):
			frappe.delete_doc(RULE_DOCTYPE, rule, force=True)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_first_rule_warns_about_roles_that_lose_access(self):
		"""Decision note, section 3: the warning lists the roles without a rule and does not stop the save."""
		admin = self.login(ADMIN)

		created = self.send(
			admin,
			"POST",
			REST + RULE_DOCTYPE,
			body={
				"title": "Uyari kurali",
				"document_type": FREE_DOCTYPE,
				"role": "ER IK",
				"scope": "all",
				"allow_read": 1,
			},
		)

		self.assertEqual(created.status_code, 200)
		self.addCleanup(self.drop_rule, created.json["data"]["name"])
		self.assertIn(ROLE_NO_RULE, created.get_data(as_text=True))

	def test_only_system_manager_manages_rules(self):
		employee = self.login(EMPLOYEE_1)

		listed = self.rest_list(employee, RULE_DOCTYPE)
		changed = self.send(
			employee, "PUT", self.rule_path(OWN_RULE), body={"scope": "all", "match_field": ""}
		)

		self.assertEqual(listed.status_code, 403)
		self.assertEqual(changed.status_code, 403)
		self.assertEqual(frappe.db.get_value(RULE_DOCTYPE, self.rules[OWN_RULE], "scope"), "own")
		self.assertTrue(frappe.db.exists(DOCTYPE, self.records[EMPLOYEE_1]))
