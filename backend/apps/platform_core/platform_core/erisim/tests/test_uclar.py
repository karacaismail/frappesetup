"""The `explain_permission` and `get_access_summary` endpoints (contract)."""

import frappe
from frappe.utils.background_jobs import get_queues

from platform_core.erisim.tests import base
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
		return self.api(
			client, "GET", "explain_permission", query={"doctype": DOCTYPE, "name": name, **query}
		)

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
		"""Contract: the endpoint does not reveal to an ordinary user that a record exists."""
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
		"""A manager reads the record of their team but cannot write it."""
		response = self.explain(self.login(ADMIN), self.records[EMPLOYEE_2], user=MANAGER_1, ptype="write")

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

	def test_unknown_doctype_is_denied_like_an_unreadable_one(self):
		"""Contract: the endpoint does not reveal that a document type exists. A missing document type also returns 403."""
		response = self.summary(self.login(EMPLOYEE_1), "ER Olmayan Tur")

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

	def test_guest_is_rejected(self):
		response = self.summary(self.anonymous())

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True))


class TestWebsiteUser(ErisimTestCase):
	"""A Website User reaches only the methods the shell allows (`website_user_allowed_methods`).

	The summary shows the user's own scopes and is open to them. The explanation shows rule
	detail and stays with desk users.
	"""

	RULES = (
		*ErisimTestCase.RULES,
		{
			"title": "Portal own records",
			"role": base.ROLE_PORTAL,
			"scope": "own",
			"match_field": "owner",
			"allow_read": 1,
			"priority": 40,
		},
	)

	def test_the_fixture_user_is_a_website_user(self):
		self.assertEqual(frappe.db.get_value("User", base.PORTAL, "user_type"), "Website User")

	def test_website_user_gets_their_own_summary(self):
		response = self.api(self.login(base.PORTAL), "GET", "get_access_summary", query={"doctype": DOCTYPE})

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		message = response.json["message"]
		self.assertTrue(message["governed"])
		self.assertEqual(message["operations"]["read"], ["own"])
		self.assertEqual(message["operations"]["write"], [])
		# Nothing about other roles, rule names or rule fields.
		self.assertEqual(set(message), {"doctype", "governed", "operations"})

	def test_website_user_cannot_ask_for_an_explanation(self):
		record = self.records[EMPLOYEE_1]
		query = {"doctype": DOCTYPE, "name": record}

		response = self.api(self.login(base.PORTAL), "GET", "explain_permission", query=query)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		self.assertNotIn("Calisan kendi kaydi", response.get_data(as_text=True))

	def test_website_user_cannot_change_levels(self):
		body = {"doctype": DOCTYPE, "role": base.ROLE_PORTAL, "permlevel": 1, "read": True, "write": False}

		response = self.api(self.login(base.PORTAL), "POST", "set_level_access", body=body)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])

	def test_summary_is_on_the_shell_allow_list_and_the_explanation_is_not(self):
		allowed = frappe.get_hooks("website_user_allowed_methods")

		self.assertIn("platform_core.api.access.get_access_summary", allowed)
		self.assertNotIn("platform_core.api.access.explain_permission", allowed)


class TestQueuedJobs(ErisimTestCase):
	def test_waiting_jobs_are_run_before_the_queue_is_full(self):
		"""A site without a worker must not fail a test because old jobs fill the queue."""
		for _number in range(5):
			frappe.enqueue("frappe.ping", queue="default")

		waited = base.run_queued_jobs(room=5)

		self.assertGreaterEqual(waited, 5)
		self.assertEqual(sum(queue.count for queue in get_queues()), 0)
