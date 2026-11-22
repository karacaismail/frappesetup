"""Who may call each endpoint of the engine (D-6).

One row for each endpoint, one column for each kind of caller. Every cell is a real request
and the expected status comes from the contract (`contracts/platform_core-erisim.openapi.yaml`)
and from section 21 of the decision note. A refusal must not carry any record of the test.

Callers:

- guest: no session;
- website user: a role without desk access, with a rule on the test type;
- desk user without a role on the test type;
- rule holder: the widest rule (`all`). No separate "rule manager" role exists yet (G-62):
  only a System Manager may change rules and levels;
- System Manager.
"""

import frappe

from platform_core.erisim.test_link_search import UNSAFE_QUERY, register_for_test
from platform_core.erisim.tests.base import (
	ADMIN,
	DESK_ONLY,
	DOCTYPE,
	HR,
	PORTAL,
	ROLE_PORTAL,
	ErisimTestCase,
)

ACCESS = "/api/method/platform_core.api.access."
SEARCH_LINK = "/api/method/frappe.desk.search.search_link"
SEARCH_WIDGET = "/api/method/frappe.desk.search.search_widget"
VALIDATE_LINK = "/api/method/frappe.client.validate_link_and_fetch"
CALLERS = ("guest", "website", "desk_only", "rule_holder", "system_manager")
USERS = {"website": PORTAL, "desk_only": DESK_ONLY, "rule_holder": HR, "system_manager": ADMIN}

# endpoint: expected status for guest, website user, desk user without a role, rule holder, System Manager
EXPECTED = {
	"explain_permission": (403, 403, 403, 200, 200),
	"get_access_summary": (403, 200, 403, 200, 200),
	"set_field_level": (403, 403, 403, 403, 200),
	"set_level_access": (403, 403, 403, 403, 200),
	"search_link": (403, 200, 403, 200, 200),
	"search_link, custom function": (403, 403, 403, 403, 403),
	"search_widget": (403, 403, 403, 200, 200),
	"search_widget, custom function": (403, 403, 403, 403, 403),
	"validate_link_and_fetch": (403, 403, 403, 200, 200),
	"validate_link_and_fetch, custom function": (403, 403, 403, 403, 403),
}

# The rule record itself, through Frappe's own document endpoints. Only a System Manager holds
# a permission on the type (decision note, section 3).
RULES_PATH = "/api/v2/document/Access Rule"
RULE_EXPECTED = {
	"list rules": (403, 403, 403, 403, 200),
	"read a rule": (403, 403, 403, 403, 200),
	"create a rule": (403, 403, 403, 403, 200),
	"change a rule": (403, 403, 403, 403, 200),
	"delete a rule": (403, 403, 403, 403, 202),
}


class TestEntryMatrix(ErisimTestCase):
	RULES = (
		*ErisimTestCase.RULES,
		{
			"title": "Portal own records",
			"role": ROLE_PORTAL,
			"scope": "own",
			"match_field": "owner",
			"allow_read": 1,
			"priority": 40,
		},
	)

	def setUp(self):
		super().setUp()
		register_for_test(self, UNSAFE_QUERY)
		self.record = self.records[HR] if HR in self.records else next(iter(self.records.values()))
		self.addCleanup(self.restore_levels)

	def restore_levels(self) -> None:
		"""The two write endpoints succeed for a System Manager. Put the type back as it was."""
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("Property Setter", {"doc_type": DOCTYPE, "property": "permlevel"})
		frappe.db.delete("Custom DocPerm", {"parent": DOCTYPE})
		frappe.clear_cache(doctype=DOCTYPE)
		# Committed on purpose: the next request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def call(self, client, endpoint: str):
		search = {"doctype": DOCTYPE, "txt": "", "page_length": 500}
		link = {"doctype": DOCTYPE, "docname": self.record}
		custom = {"query": UNSAFE_QUERY}
		requests = {
			"explain_permission": (
				"GET",
				ACCESS + "explain_permission",
				{"query": {"doctype": DOCTYPE, "name": self.record}},
			),
			"get_access_summary": ("GET", ACCESS + "get_access_summary", {"query": {"doctype": DOCTYPE}}),
			"set_field_level": (
				"POST",
				ACCESS + "set_field_level",
				{"body": {"doctype": DOCTYPE, "fieldname": "status", "permlevel": 1}},
			),
			"set_level_access": (
				"POST",
				ACCESS + "set_level_access",
				{
					"body": {
						"doctype": DOCTYPE,
						"role": ROLE_PORTAL,
						"permlevel": 1,
						"read": True,
						"write": False,
					}
				},
			),
			"search_link": ("POST", SEARCH_LINK, {"body": search}),
			"search_link, custom function": ("POST", SEARCH_LINK, {"body": {**search, **custom}}),
			"search_widget": ("POST", SEARCH_WIDGET, {"body": search}),
			"search_widget, custom function": ("POST", SEARCH_WIDGET, {"body": {**search, **custom}}),
			"validate_link_and_fetch": ("POST", VALIDATE_LINK, {"body": link}),
			"validate_link_and_fetch, custom function": ("POST", VALIDATE_LINK, {"body": {**link, **custom}}),
		}
		method, path, arguments = requests[endpoint]
		return self.send(client, method, path, **arguments)

	def test_every_endpoint_for_every_kind_of_caller(self):
		clients = {caller: self.login(user) for caller, user in USERS.items()}
		clients["guest"] = self.anonymous()
		for endpoint, statuses in EXPECTED.items():
			for caller, expected in zip(CALLERS, statuses, strict=True):
				with self.subTest(endpoint=endpoint, caller=caller):
					response = self.call(clients[caller], endpoint)
					body = response.get_data(as_text=True)
					self.assertEqual(response.status_code, expected, body[:300])
					if expected == 403:
						for name in self.records.values():
							self.assertNotIn(name, body)
				if endpoint.startswith("set_"):
					self.restore_levels()

	def rule_call(self, client, action: str):
		rule = f"{RULES_PATH}/{self.spare_rule}"
		new = {
			"title": "Matrix rule",
			"document_type": DOCTYPE,
			"role": ROLE_PORTAL,
			"scope": "all",
			"allow_read": 1,
			"is_active": 0,
		}
		requests = {
			"list rules": ("GET", RULES_PATH, {}),
			"read a rule": ("GET", rule, {}),
			"create a rule": ("POST", RULES_PATH, {"body": new}),
			"change a rule": ("PUT", rule, {"body": {"description": "Changed by the matrix test"}}),
			"delete a rule": ("DELETE", rule, {}),
		}
		method, path, arguments = requests[action]
		return self.send(client, method, path, **arguments)

	def test_the_rule_record_for_every_kind_of_caller(self):
		spare = {**self.RULES[-1], "title": "Spare rule of the matrix", "is_active": 0}
		self.spare_rule = (
			frappe.get_doc({"doctype": "Access Rule", "document_type": DOCTYPE, **spare}).insert().name
		)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		clients = {caller: self.login(user) for caller, user in USERS.items()}
		clients["guest"] = self.anonymous()
		before = frappe.db.count("Access Rule")
		for action, statuses in RULE_EXPECTED.items():
			for caller, expected in zip(CALLERS, statuses, strict=True):
				with self.subTest(action=action, caller=caller):
					response = self.rule_call(clients[caller], action)
					body = response.get_data(as_text=True)
					self.assertEqual(response.status_code, expected, body[:300])
					if expected == 403:
						self.assertNotIn("Spare rule of the matrix", body)
						frappe.db.rollback()
						self.assertEqual(frappe.db.count("Access Rule"), before)
			if action == "create a rule":
				frappe.db.rollback()
				before = frappe.db.count("Access Rule")

	def test_refused_writes_change_nothing(self):
		for caller in ("guest", "website", "desk_only", "rule_holder"):
			client = self.anonymous() if caller == "guest" else self.login(USERS[caller])
			with self.subTest(caller=caller):
				self.call(client, "set_field_level")
				self.call(client, "set_level_access")
				frappe.db.rollback()
				self.assertEqual(frappe.get_meta(DOCTYPE).get_field("status").permlevel, 0)
				self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))

	def test_the_table_names_every_endpoint_of_the_engine(self):
		"""A new endpoint must get its row here."""
		from platform_core.api import access
		from platform_core.erisim import link_search

		endpoints = {
			function.__name__
			for module in (access, link_search)
			for function in vars(module).values()
			if callable(function)
			and function in frappe.whitelisted
			and function.__module__ == module.__name__
		}

		self.assertEqual(endpoints, {name.split(",")[0] for name in EXPECTED})

	def test_website_user_search_shows_only_their_own_records(self):
		own = frappe.get_doc({"doctype": DOCTYPE, "title": "Portal record"}).insert().name
		frappe.db.set_value(DOCTYPE, own, "owner", PORTAL)
		self.addCleanup(frappe.delete_doc, DOCTYPE, own, force=True)

		response = self.send(
			self.login(PORTAL), "POST", SEARCH_LINK, body={"doctype": DOCTYPE, "txt": "", "page_length": 500}
		)

		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		self.assertEqual({row["value"] for row in response.json["message"]}, {own})
