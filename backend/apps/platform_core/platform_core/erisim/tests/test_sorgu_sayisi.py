"""Query count: a rule does not cause one query per record (P-1)."""

from collections import defaultdict

import frappe

from platform_core.erisim.tests.base import DOCTYPE, EMPLOYEE_2, MANAGER_1, ErisimTestCase

EXTRA_RECORDS = 40


class TestQueryCount(ErisimTestCase):
	def count_list_queries(self, user: str) -> tuple[int, int]:
		"""Reads the list of the user. Returns the query count and the number of records returned."""
		queries = []
		original = frappe.db.__class__.sql

		def counting_sql(*args, **kwargs):
			queries.append(args[1] if len(args) > 1 else kwargs.get("query"))
			return original(*args, **kwargs)

		frappe.set_user(user)
		# The first read puts the document type definition and the roles in the cache. The measurement is the second read.
		frappe.get_list(DOCTYPE, fields=["name", "title"], limit=1000)
		# A real request starts with an empty request cache, so the engine's own queries are counted.
		frappe.local.request_cache = defaultdict(dict)
		self.addCleanup(self.drop_request_cache)
		frappe.db.__class__.sql = counting_sql
		try:
			rows = frappe.get_list(DOCTYPE, fields=["name", "title"], limit=1000)
		finally:
			frappe.db.__class__.sql = original
			frappe.set_user("Administrator")
		return len(queries), len(rows)

	def drop_request_cache(self) -> None:
		if hasattr(frappe.local, "request_cache"):
			del frappe.local.request_cache

	def test_list_query_count_does_not_grow_with_record_count(self):
		before, visible_before = self.count_list_queries(MANAGER_1)
		for number in range(EXTRA_RECORDS):
			self.insert_record(EMPLOYEE_2, title=f"Ek talep {number}")

		after, visible_after = self.count_list_queries(MANAGER_1)

		self.assertEqual(visible_after, visible_before + EXTRA_RECORDS)
		self.assertEqual(after, before)

	def test_rule_adds_a_small_fixed_number_of_queries(self):
		"""Decision note, section 7: at most 2 queries for the subject, at most 1 query for the rule list."""
		with_rules, _visible = self.count_list_queries(MANAGER_1)
		frappe.db.set_value("Access Rule", {"document_type": DOCTYPE}, "is_active", 0)

		without_rules, _all = self.count_list_queries(MANAGER_1)

		self.assertGreater(with_rules, without_rules - 1)
		self.assertLessEqual(with_rules - without_rules, 3)
