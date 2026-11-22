"""Sorgu sayısı: kural yüzünden kayıt başına sorgu açılmaz (P-1)."""

import frappe

from platform_core.erisim.rules import CACHE_KEY
from platform_core.erisim.tests.base import DOCTYPE, EMPLOYEE_2, MANAGER_1, ErisimTestCase

EXTRA_RECORDS = 40


class TestQueryCount(ErisimTestCase):
	def count_list_queries(self, user: str) -> tuple[int, int]:
		"""Kullanıcının listesini okur. Sorgu sayısını ve dönen kayıt sayısını verir."""
		queries = []
		original = frappe.db.__class__.sql

		def counting_sql(*args, **kwargs):
			queries.append(args[1] if len(args) > 1 else kwargs.get("query"))
			return original(*args, **kwargs)

		frappe.set_user(user)
		# İlk okuma kayıt türü tanımını ve rolleri önbelleğe alır. Ölçüm ikinci okumadır.
		frappe.get_list(DOCTYPE, fields=["name", "title"], limit=1000)
		# Kural önbelleği silinir. Böylece motorun kendi sorguları ölçüme girer.
		frappe.cache.delete_value(CACHE_KEY)
		frappe.db.__class__.sql = counting_sql
		try:
			rows = frappe.get_list(DOCTYPE, fields=["name", "title"], limit=1000)
		finally:
			frappe.db.__class__.sql = original
			frappe.set_user("Administrator")
		return len(queries), len(rows)

	def test_list_query_count_does_not_grow_with_record_count(self):
		before, visible_before = self.count_list_queries(MANAGER_1)
		for number in range(EXTRA_RECORDS):
			self.insert_record(EMPLOYEE_2, title=f"Ek talep {number}")

		after, visible_after = self.count_list_queries(MANAGER_1)

		self.assertEqual(visible_after, visible_before + EXTRA_RECORDS)
		self.assertEqual(after, before)

	def test_rule_adds_a_small_fixed_number_of_queries(self):
		"""Karar notu 7. bölüm: özne için en çok 2 sorgu, kural listesi için en çok 1 sorgu."""
		with_rules, _visible = self.count_list_queries(MANAGER_1)
		frappe.db.set_value("Access Rule", {"document_type": DOCTYPE}, "is_active", 0)

		without_rules, _all = self.count_list_queries(MANAGER_1)

		self.assertGreater(with_rules, without_rules - 1)
		self.assertLessEqual(with_rules - without_rules, 3)
