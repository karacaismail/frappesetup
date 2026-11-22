"""The rules kept for one request must never outlive a change made in that request (review O1).

A partial rollback (`frappe.db.rollback(save_point=...)`) does not fire Frappe's rollback
callbacks (`frappe/database/database.py:1212`). So after a rule changed in a request, the
engine stops keeping rules for the rest of that request and reads them from the database.
"""

from collections import defaultdict

import frappe

from platform_core.access import rules
from platform_core.access.tests.base import DOCTYPE, EMPLOYEE_1, EMPLOYEE_2, RULE_DOCTYPE, AccessRuleTestCase

OWN_RULE = "Calisan kendi kaydi"


class TestRuleCacheWithinARequest(AccessRuleTestCase):
	def setUp(self):
		super().setUp()
		# A real request has a request cache. The test process has none, so it gets one here.
		frappe.local.request_cache = defaultdict(dict)
		self.addCleanup(self.drop_request_cache)
		# Committed on purpose: start from a clean transaction.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def drop_request_cache(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		# A new request starts with an empty cache. The cache itself stays, for the tests that follow.
		frappe.local.request_cache = defaultdict(dict)

	def employee_reads_other_record(self) -> bool:
		return frappe.has_permission(DOCTYPE, "read", doc=self.records[EMPLOYEE_2], user=EMPLOYEE_1)

	def widen_own_rule(self) -> None:
		rule = frappe.get_doc(RULE_DOCTYPE, self.rules[OWN_RULE])
		rule.update({"scope": "all", "match_field": None})
		rule.save()

	def test_rules_are_kept_for_the_request_while_nothing_changes(self):
		self.assertFalse(self.employee_reads_other_record())

		with self.assertQueryCount(0):
			rules.rules_for(DOCTYPE)

	def test_partial_rollback_restores_the_narrow_rule(self):
		self.assertFalse(self.employee_reads_other_record())
		frappe.db.savepoint("before_widening")

		self.widen_own_rule()
		self.assertTrue(self.employee_reads_other_record())
		frappe.db.rollback(save_point="before_widening")

		self.assertFalse(self.employee_reads_other_record())
		self.assertEqual(
			[rule["scope"] for rule in rules.rules_for(DOCTYPE) if rule["title"] == OWN_RULE], ["own"]
		)

	def test_full_rollback_restores_the_narrow_rule(self):
		self.assertFalse(self.employee_reads_other_record())

		self.widen_own_rule()
		self.assertTrue(self.employee_reads_other_record())
		frappe.db.rollback()

		self.assertFalse(self.employee_reads_other_record())

	def test_change_is_seen_at_once_in_the_same_request(self):
		self.assertFalse(self.employee_reads_other_record())

		self.widen_own_rule()

		self.assertTrue(self.employee_reads_other_record())
