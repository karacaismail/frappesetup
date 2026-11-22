"""Link searches on governed document types.

Rule: on a governed document type only Frappe's standard search runs. Every custom search
function is refused, for every user. There is no allow-list: whether a function reads with
permissions cannot be verified from its code.
"""

import inspect
import re
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe import client as frappe_client
from frappe.desk import search as frappe_search

import platform_core
from platform_core.erisim import api, link_search
from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	EMPLOYEE_2,
	FREE_DOCTYPE,
	HR,
	NO_RULE,
	ErisimTestCase,
)

SEARCH_LINK = "/api/method/frappe.desk.search.search_link"
SEARCH_WIDGET = "/api/method/frappe.desk.search.search_widget"
LINK_VALIDATION = "frappe.client.validate_link_and_fetch"
VALIDATE_LINK = "/api/method/" + LINK_VALIDATION
UNSAFE_QUERY = "platform_core.erisim.test_link_search.unscoped_query"
SAFE_LOOKING_QUERY = "platform_core.erisim.test_link_search.safe_looking_query"
SALARY = 987653


@frappe.validate_and_sanitize_search_inputs
def unscoped_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""A careless custom search: it returns every record and a restricted field.

	It is not an endpoint. It carries no whitelist decorator, so the shipped package cannot be
	asked to run it over HTTP. `register_for_test` makes Frappe accept it during one test only.
	"""
	# System read on purpose: the test needs a search that ignores record rules.
	return frappe.get_all(doctype, fields=["name", "title", "salary_amount"], as_list=True, limit=500)


@frappe.validate_and_sanitize_search_inputs
def safe_looking_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""A search that looks careful but reads as another user. It is not an endpoint either."""
	return frappe.get_list(doctype, fields=["name", "title"], user="Administrator", as_list=True, limit=500)


def register_for_test(test, *paths: str) -> None:
	"""Let Frappe call the functions as search functions until the test ends."""
	for path in paths:
		function = frappe.get_attr(path)
		frappe.whitelisted.add(function)
		frappe.allowed_http_methods_for_whitelisted_func[function] = ["GET", "POST"]
		test.addCleanup(frappe.whitelisted.discard, function)
		test.addCleanup(frappe.allowed_http_methods_for_whitelisted_func.pop, function, None)


class TestLinkSearch(ErisimTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.set_value(DOCTYPE, cls.records[EMPLOYEE_1], "salary_amount", SALARY)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def setUp(self):
		super().setUp()
		register_for_test(self, UNSAFE_QUERY, SAFE_LOOKING_QUERY)

	def search(self, client, path: str = SEARCH_LINK, doctype: str = DOCTYPE, **extra):
		body = {"doctype": doctype, "txt": "", "page_length": 500, **extra}
		return self.send(client, "POST", path, body=body)

	def values(self, response) -> set[str]:
		self.assertEqual(response.status_code, 200)
		rows = response.json["message"]
		return {row["value"] if isinstance(row, dict) else row[0] for row in rows}

	def assert_refused(self, response) -> None:
		self.assertEqual(response.status_code, 403)
		body = response.get_data(as_text=True)
		self.assertFalse(str(SALARY) in body, "the response carries a value it must not carry")
		for name in self.records.values():
			self.assertFalse(name in body, "the response carries a value it must not carry")

	def test_search_link_guest_denied(self):
		self.assert_refused(self.search(self.anonymous(), query=UNSAFE_QUERY))

	def test_search_widget_guest_denied(self):
		self.assert_refused(self.search(self.anonymous(), SEARCH_WIDGET, query=UNSAFE_QUERY))

	def test_search_link_foreign_data_denied(self):
		"""A custom search that is not on the allow-list is refused on a governed type."""
		self.assert_refused(self.search(self.login(EMPLOYEE_1), query=UNSAFE_QUERY))

	def test_search_widget_foreign_data_denied(self):
		self.assert_refused(self.search(self.login(EMPLOYEE_1), SEARCH_WIDGET, query=UNSAFE_QUERY))

	def test_refusal_does_not_depend_on_how_much_the_user_sees(self):
		for user in (HR, NO_RULE, ADMIN):
			with self.subTest(user=user):
				self.assert_refused(self.search(self.login(user), query=UNSAFE_QUERY))

	def test_standard_query_hook_is_refused_too(self):
		"""An app can also set the search of a document type through `standard_queries`."""
		original = frappe.get_hooks

		def with_standard_query(hook=None, *args, **kwargs):
			hooks = original(hook, *args, **kwargs)
			if hook is None:
				hooks = frappe._dict(hooks)
				hooks["standard_queries"] = {**(hooks.get("standard_queries") or {}), DOCTYPE: [UNSAFE_QUERY]}
			return hooks

		client = self.login(EMPLOYEE_1)
		with patch.object(frappe, "get_hooks", with_standard_query):
			response = self.search(client)

		self.assert_refused(response)

	def test_administrator_is_refused_too(self):
		"""Review O2: the rule has no exception. Frappe's own search would run the function."""
		frappe.set_user("Administrator")

		for function in (link_search.search_link, link_search.search_widget):
			with self.subTest(function=function.__name__):
				self.assertRaises(frappe.PermissionError, function, DOCTYPE, "", UNSAFE_QUERY)
		self.assertRaises(frappe.PermissionError, api.link_search_guard, DOCTYPE, UNSAFE_QUERY)

	def test_administrator_is_refused_for_a_standard_query_hook_too(self):
		original = frappe.get_hooks

		def with_standard_query(hook=None, *args, **kwargs):
			hooks = original(hook, *args, **kwargs)
			if hook is None:
				hooks = frappe._dict(hooks)
				hooks["standard_queries"] = {**(hooks.get("standard_queries") or {}), DOCTYPE: [UNSAFE_QUERY]}
			return hooks

		frappe.set_user("Administrator")
		with patch.object(frappe, "get_hooks", with_standard_query):
			for function in (link_search.search_link, link_search.search_widget):
				with self.subTest(function=function.__name__):
					self.assertRaises(frappe.PermissionError, function, DOCTYPE, "")

	def test_administrator_keeps_the_standard_search(self):
		frappe.set_user("Administrator")

		values = {row["value"] for row in link_search.search_link(DOCTYPE, "", page_length=500)}

		self.assertEqual(values, set(self.records.values()))

	def test_function_that_looks_permission_aware_is_refused_too(self):
		for user in (EMPLOYEE_1, HR):
			with self.subTest(user=user):
				self.assert_refused(self.search(self.login(user), query=SAFE_LOOKING_QUERY))

	def test_app_allow_list_does_not_open_a_custom_search(self):
		"""The `access_rule_allowed_queries` hook is gone. Listing a function changes nothing."""
		original = frappe.get_hooks

		def with_allow_list(hook=None, *args, **kwargs):
			if hook in ("access_rule_allowed_queries", "access_rule_verified_queries"):
				return [UNSAFE_QUERY, SAFE_LOOKING_QUERY]
			return original(hook, *args, **kwargs)

		client = self.login(EMPLOYEE_1)
		with patch.object(frappe, "get_hooks", with_allow_list):
			responses = [self.search(client, query=query) for query in (UNSAFE_QUERY, SAFE_LOOKING_QUERY)]

		for response in responses:
			self.assert_refused(response)
		for name in ("allowed_queries", "verified_queries", "ALLOWED_QUERIES_HOOK", "query_source"):
			self.assertFalse(hasattr(link_search, name), name)

	def test_standard_search_is_unchanged(self):
		governed = self.search(self.login(EMPLOYEE_1))
		name = frappe.get_doc({"doctype": FREE_DOCTYPE, "title": "Free"}).insert().name
		self.addCleanup(frappe.delete_doc, FREE_DOCTYPE, name, force=True)
		free = self.search(self.login(NO_RULE), doctype=FREE_DOCTYPE)

		self.assertEqual(self.values(governed), {self.records[EMPLOYEE_1]})
		self.assertIn(name, self.values(free))

	def test_custom_search_on_an_ungoverned_type_is_left_to_frappe(self):
		name = frappe.get_doc({"doctype": FREE_DOCTYPE, "title": "Free"}).insert().name
		self.addCleanup(frappe.delete_doc, FREE_DOCTYPE, name, force=True)

		response = self.search(self.login(NO_RULE), doctype=FREE_DOCTYPE, query=SAFE_LOOKING_QUERY)

		self.assertIn(name, self.values(response))

	def validate_link(self, client, docname: str, **extra):
		body = {"doctype": DOCTYPE, "docname": docname, **extra}
		return self.send(client, "POST", VALIDATE_LINK, body=body)

	def test_validate_link_and_fetch_guest_denied(self):
		response = self.validate_link(self.anonymous(), self.records[EMPLOYEE_1], query=UNSAFE_QUERY)

		self.assert_refused(response)

	def test_validate_link_and_fetch_foreign_data_denied(self):
		"""Frappe's link validation calls the search from Python and would run the custom function.

		`frappe/client.py:459`. The careless function finds the record, and the endpoint would
		then confirm that a record the user cannot see exists.
		"""
		foreign = self.records[EMPLOYEE_2]
		for user in (EMPLOYEE_1, HR, ADMIN):
			with self.subTest(user=user):
				self.assert_refused(self.validate_link(self.login(user), foreign, query=UNSAFE_QUERY))

	def test_link_validation_through_a_standard_query_hook_is_refused_too(self):
		original = frappe.get_hooks

		def with_standard_query(hook=None, *args, **kwargs):
			hooks = original(hook, *args, **kwargs)
			if hook is None:
				hooks = frappe._dict(hooks)
				hooks["standard_queries"] = {**(hooks.get("standard_queries") or {}), DOCTYPE: [UNSAFE_QUERY]}
			return hooks

		client = self.login(EMPLOYEE_1)
		with patch.object(frappe, "get_hooks", with_standard_query):
			response = self.validate_link(client, self.records[EMPLOYEE_2])

		self.assert_refused(response)

	def test_standard_link_validation_is_unchanged(self):
		client = self.login(EMPLOYEE_1)
		own = self.validate_link(client, self.records[EMPLOYEE_1])
		foreign = self.validate_link(client, self.records[EMPLOYEE_2])

		self.assertEqual(own.status_code, 200)
		self.assertEqual(own.json["message"], {"name": self.records[EMPLOYEE_1]})
		self.assertEqual(foreign.status_code, 200)
		self.assertFalse(foreign.json["message"])

	def test_replacements_accept_every_argument_of_the_frappe_function(self):
		"""An argument the replacement does not know is dropped without a word. A Frappe upgrade shows here."""
		pairs = (
			(link_search.search_link, frappe_search.search_link),
			(link_search.search_widget, frappe_search.search_widget),
			(link_search.validate_link_and_fetch, frappe_client.validate_link_and_fetch),
		)
		for ours, theirs in pairs:
			with self.subTest(function=ours.__name__):
				missing = set(inspect.signature(theirs).parameters) - set(inspect.signature(ours).parameters)
				self.assertEqual(missing, set())

	def test_every_replacement_is_registered(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		for name in ("frappe.desk.search.search_link", "frappe.desk.search.search_widget", LINK_VALIDATION):
			with self.subTest(name=name):
				self.assertEqual(
					overrides.get(name), ["platform_core.erisim.link_search." + name.rsplit(".", 1)[1]]
				)

	def test_refusal_does_not_echo_markup_from_the_request(self):
		response = self.search(self.login(EMPLOYEE_1), query="<img src=x onerror=alert(1)>" + UNSAFE_QUERY)

		self.assertFalse(
			"<img" in response.get_data(as_text=True), "the response carries a value it must not carry"
		)

	def test_python_callers_get_the_same_refusal_from_the_public_guard(self):
		frappe.set_user(EMPLOYEE_1)

		self.assertRaises(frappe.PermissionError, api.link_search_guard, DOCTYPE, UNSAFE_QUERY)
		self.assertRaises(frappe.PermissionError, api.search_link, DOCTYPE, "", UNSAFE_QUERY)
		self.assertIsNone(api.link_search_guard(DOCTYPE, None))

	def test_test_helpers_are_not_endpoints_outside_a_test(self):
		"""Without `register_for_test` Frappe refuses to call the helper functions at all."""
		for path in (UNSAFE_QUERY, SAFE_LOOKING_QUERY):
			function = frappe.get_attr(path)
			frappe.whitelisted.discard(function)
			self.assertNotIn(function, frappe.whitelisted)
			self.assertNotIn(function, frappe.guest_methods)
		client = self.login(EMPLOYEE_1)

		direct = self.send(client, "POST", "/api/method/" + UNSAFE_QUERY, body={"doctype": DOCTYPE})
		through_search = self.search(client, doctype=FREE_DOCTYPE, query=UNSAFE_QUERY)

		for response in (direct, through_search):
			body = response.get_data(as_text=True)
			self.assertNotEqual(response.status_code, 200)
			self.assertFalse(str(SALARY) in body, "the response carries a value it must not carry")

	def test_no_test_file_in_the_package_declares_an_endpoint(self):
		"""Test files ship with the app. A whitelisted function in one would be a live endpoint."""
		root = Path(platform_core.__file__).parent
		# Matches the decorator and the call, whether `frappe` is spelled out or the name was imported.
		endpoint = re.compile(r"(^|[^\w.])(frappe\.)?whitelist\s*\(|import\s+.*\bwhitelist\b")
		offenders = [
			str(path.relative_to(root))
			for path in root.rglob("*.py")
			if (path.name.startswith("test_") or "tests" in path.relative_to(root).parts)
			and any(endpoint.search(line) for line in path.read_text().splitlines())
		]

		self.assertEqual(offenders, [])

	def test_no_platform_code_calls_frappes_search_directly(self):
		"""Frappe's own search function cannot be intercepted from Python. Our code must not call it.

		Naming the endpoint in a string is fine: hooks and the shell's allow-list do that.
		"""
		root = Path(platform_core.__file__).parent
		reaches_search = re.compile(
			r"from\s+frappe\.desk\.search\s+import|from\s+frappe\.desk\s+import\s+[^\n]*\bsearch\b"
			r"|import\s+frappe\.desk\.search|(?<![\"'\w.])frappe\.desk\.search\.\w+\s*\("
			r"|get_attr\(\s*[\"']frappe\.desk\.search"
		)
		allowed = {root / "erisim" / "link_search.py"}
		offenders = [
			str(path.relative_to(root))
			for path in root.rglob("*.py")
			if path not in allowed
			and not path.name.startswith("test_")
			and reaches_search.search(path.read_text())
		]

		self.assertEqual(offenders, [])
