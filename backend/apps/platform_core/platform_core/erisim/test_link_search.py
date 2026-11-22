"""Link searches on governed document types.

Rule: on a governed document type only Frappe's standard search and search functions on the
engine's allow-list run. An allow-listed function must itself read through permission-aware
calls. Every other custom search function is refused.
"""

import re
from pathlib import Path
from unittest.mock import patch

import frappe

import platform_core
from platform_core.erisim import api, link_search
from platform_core.erisim.tests.base import (
	ADMIN,
	DOCTYPE,
	EMPLOYEE_1,
	FREE_DOCTYPE,
	HR,
	NO_RULE,
	ErisimTestCase,
)

SEARCH_LINK = "/api/method/frappe.desk.search.search_link"
SEARCH_WIDGET = "/api/method/frappe.desk.search.search_widget"
UNSAFE_QUERY = "platform_core.erisim.test_link_search.unscoped_query"
SAFE_QUERY = "platform_core.erisim.tests.test_support_safe_query.scoped_query"
SALARY = 987653


@frappe.validate_and_sanitize_search_inputs
def unscoped_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""A careless custom search: it returns every record and a restricted field.

	It is not an endpoint. It carries no whitelist decorator, so the shipped package cannot be
	asked to run it over HTTP. `register_for_test` makes Frappe accept it during one test only.
	"""
	# System read on purpose: the test needs a search that ignores record rules.
	return frappe.get_all(doctype, fields=["name", "title", "salary_amount"], as_list=True, limit=500)


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
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def setUp(self):
		super().setUp()
		register_for_test(self, UNSAFE_QUERY, SAFE_QUERY)

	def search(self, client, path: str = SEARCH_LINK, doctype: str = DOCTYPE, **extra):
		body = {"doctype": doctype, "txt": "", "page_length": 500, **extra}
		return self.send(client, "POST", path, body=body)

	def values(self, response) -> set[str]:
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		rows = response.json["message"]
		return {row["value"] if isinstance(row, dict) else row[0] for row in rows}

	def assert_refused(self, response) -> None:
		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])
		body = response.get_data(as_text=True)
		self.assertNotIn(str(SALARY), body)
		for name in self.records.values():
			self.assertNotIn(name, body)

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

	def test_allow_listed_unsafe_function_is_still_refused(self):
		"""Being on the list is not enough: the function must read through permission-aware calls."""
		with patch.object(link_search, "allowed_queries", return_value={UNSAFE_QUERY}):
			response = self.search(self.login(EMPLOYEE_1), query=UNSAFE_QUERY)

		self.assert_refused(response)

	def test_allow_listed_safe_function_runs_and_respects_the_rule(self):
		with patch.object(link_search, "allowed_queries", return_value={SAFE_QUERY}):
			response = self.search(self.login(EMPLOYEE_1), query=SAFE_QUERY)

		self.assertEqual(self.values(response), {self.records[EMPLOYEE_1]})
		self.assertNotIn(str(SALARY), response.get_data(as_text=True))

	def test_safe_function_that_is_not_allow_listed_is_refused(self):
		self.assert_refused(self.search(self.login(EMPLOYEE_1), query=SAFE_QUERY))

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

		response = self.search(self.login(NO_RULE), doctype=FREE_DOCTYPE, query=SAFE_QUERY)

		self.assertIn(name, self.values(response))

	def test_python_callers_get_the_same_refusal_from_the_public_guard(self):
		frappe.set_user(EMPLOYEE_1)

		self.assertRaises(frappe.PermissionError, api.link_search_guard, DOCTYPE, UNSAFE_QUERY)
		self.assertRaises(frappe.PermissionError, api.search_link, DOCTYPE, "", UNSAFE_QUERY)
		self.assertIsNone(api.link_search_guard(DOCTYPE, None))

	def test_test_helpers_are_not_endpoints_outside_a_test(self):
		"""Without `register_for_test` Frappe refuses to call the helper functions at all."""
		for path in (UNSAFE_QUERY, SAFE_QUERY):
			function = frappe.get_attr(path)
			frappe.whitelisted.discard(function)
			self.assertNotIn(function, frappe.whitelisted)
			self.assertNotIn(function, frappe.guest_methods)
		client = self.login(EMPLOYEE_1)

		direct = self.send(client, "POST", "/api/method/" + UNSAFE_QUERY, body={"doctype": DOCTYPE})
		through_search = self.search(client, doctype=FREE_DOCTYPE, query=UNSAFE_QUERY)

		for response in (direct, through_search):
			body = response.get_data(as_text=True)
			self.assertNotEqual(response.status_code, 200, body[:300])
			self.assertNotIn(str(SALARY), body)

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
		"""Frappe's own search function cannot be intercepted from Python. Our code must not call it."""
		root = Path(platform_core.__file__).parent
		# `hooks.py` only names the two endpoints it replaces.
		allowed = {root / "erisim" / "link_search.py", root / "hooks.py"}
		offenders = [
			str(path.relative_to(root))
			for path in root.rglob("*.py")
			if path not in allowed
			and not path.name.startswith("test_")
			and "frappe.desk.search"
			in path.read_text().replace("from frappe.desk import search", "frappe.desk.search")
		]

		self.assertEqual(offenders, [])
