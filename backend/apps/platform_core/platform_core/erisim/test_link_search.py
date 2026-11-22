"""Link searches on governed document types (third review, decision 5).

A link field or an app can name its own search function. Frappe returns what that function
returns (`frappe/desk/search.py:133`). The engine therefore filters the result itself.
"""

from unittest.mock import patch

import frappe

from platform_core.erisim import link_search
from platform_core.erisim.tests.base import DOCTYPE, EMPLOYEE_1, FREE_DOCTYPE, HR, NO_RULE, ErisimTestCase

SEARCH_LINK = "/api/method/frappe.desk.search.search_link"
SEARCH_WIDGET = "/api/method/frappe.desk.search.search_widget"
CUSTOM_QUERY = "platform_core.erisim.test_link_search.unscoped_query"
SALARY = 987653


@frappe.whitelist(methods=["GET", "POST"])
@frappe.validate_and_sanitize_search_inputs
def unscoped_query(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	"""A careless custom search: it returns every record and a restricted field."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw("Not permitted", frappe.PermissionError)
	# System read on purpose: the test needs a search that ignores record rules.
	return frappe.get_all(doctype, fields=["name", "title", "salary_amount"], as_list=True, limit=500)


class TestLinkSearch(ErisimTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.set_value(DOCTYPE, cls.records[EMPLOYEE_1], "salary_amount", SALARY)
		frappe.db.commit()  # nosemgrep: the request uses another connection

	def search(self, client, path: str = SEARCH_LINK, doctype: str = DOCTYPE, **extra):
		body = {"doctype": doctype, "txt": "", "page_length": 500, **extra}
		return self.send(client, "POST", path, body=body)

	def values(self, response) -> set[str]:
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
		rows = response.json["message"]
		return {row["value"] if isinstance(row, dict) else row[0] for row in rows}

	def test_search_link_guest_denied(self):
		response = self.search(self.anonymous(), query=CUSTOM_QUERY)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])

	def test_search_widget_guest_denied(self):
		response = self.search(self.anonymous(), SEARCH_WIDGET, query=CUSTOM_QUERY)

		self.assertEqual(response.status_code, 403, response.get_data(as_text=True)[:300])

	def test_search_link_foreign_data_denied(self):
		"""The custom search returns every record. The employee still gets only their own."""
		response = self.search(self.login(EMPLOYEE_1), query=CUSTOM_QUERY)

		self.assertEqual(self.values(response), {self.records[EMPLOYEE_1]})
		self.assertNotIn(str(SALARY), response.get_data(as_text=True))

	def test_search_widget_foreign_data_denied(self):
		response = self.search(self.login(EMPLOYEE_1), SEARCH_WIDGET, query=CUSTOM_QUERY)

		self.assertEqual(self.values(response), {self.records[EMPLOYEE_1]})
		self.assertNotIn(str(SALARY), response.get_data(as_text=True))

	def test_standard_query_hook_is_filtered_too(self):
		"""An app can also set the search of a document type through `standard_queries`."""
		original = frappe.get_hooks

		def with_standard_query(hook=None, *args, **kwargs):
			hooks = original(hook, *args, **kwargs)
			if hook is None:
				hooks = frappe._dict(hooks)
				hooks["standard_queries"] = {**(hooks.get("standard_queries") or {}), DOCTYPE: [CUSTOM_QUERY]}
			return hooks

		client = self.login(EMPLOYEE_1)
		with patch.object(frappe, "get_hooks", with_standard_query):
			response = self.search(client)

		self.assertEqual(self.values(response), {self.records[EMPLOYEE_1]})
		self.assertNotIn(str(SALARY), response.get_data(as_text=True))

	def test_role_without_rule_gets_nothing_from_a_custom_search(self):
		response = self.search(self.login(NO_RULE), query=CUSTOM_QUERY)

		self.assertEqual(self.values(response), set())

	def test_user_who_sees_everything_keeps_the_full_result(self):
		response = self.search(self.login(HR), query=CUSTOM_QUERY)

		self.assertEqual(self.values(response), set(self.records.values()))
		self.assertIn(str(SALARY), response.get_data(as_text=True))

	def test_verified_query_is_returned_as_is(self):
		"""An app vouches for a search with the `access_rule_verified_queries` hook."""
		with patch.object(link_search, "verified_queries", return_value={CUSTOM_QUERY}):
			response = self.search(self.login(EMPLOYEE_1), query=CUSTOM_QUERY)

		self.assertEqual(self.values(response), set(self.records.values()))

	def test_default_search_is_unchanged(self):
		governed = self.search(self.login(EMPLOYEE_1))
		name = frappe.get_doc({"doctype": FREE_DOCTYPE, "title": "Free"}).insert().name
		self.addCleanup(frappe.delete_doc, FREE_DOCTYPE, name, force=True)
		free = self.search(self.login(NO_RULE), doctype=FREE_DOCTYPE)

		self.assertEqual(self.values(governed), {self.records[EMPLOYEE_1]})
		self.assertIn(name, self.values(free))
