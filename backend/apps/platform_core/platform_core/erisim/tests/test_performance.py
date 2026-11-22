"""The hand-started measurement must leave a site as it found it (review of 9c7d6d8)."""

from unittest.mock import patch

import frappe

from platform_core.erisim.tests import performance
from platform_core.erisim.tests.base import DOCTYPE, FREE_DOCTYPE, ROLE_HR, RULE_DOCTYPE, ErisimTestCase

SMALL = {"calls": 50, "employees": 12, "records": 40}


class TestMeasurementCleansOnlyItsOwn(ErisimTestCase):
	def setUp(self):
		super().setUp()
		# A rule and a record that were on the site before the measurement.
		self.old_rule = (
			frappe.get_doc(
				{
					"doctype": RULE_DOCTYPE,
					"title": "Older rule of the site",
					"document_type": FREE_DOCTYPE,
					"role": ROLE_HR,
					"scope": "all",
					"allow_read": 1,
					"is_active": 1,
				}
			)
			.insert()
			.name
		)
		self.old_records = set(self.records.values())
		# Committed on purpose: the measurement commits and its requests use another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		self.addCleanup(self.remove_old_rule)

	def remove_old_rule(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.delete_doc(RULE_DOCTYPE, self.old_rule, force=True)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def assert_site_as_before(self) -> None:
		frappe.db.rollback()
		self.assertTrue(frappe.db.exists(RULE_DOCTYPE, self.old_rule))
		for name in self.rules.values():
			self.assertTrue(frappe.db.exists(RULE_DOCTYPE, name), name)
		self.assertEqual(set(frappe.get_all(DOCTYPE, pluck="name", limit=0)), self.old_records)
		self.assertFalse(frappe.db.count("Employee", {"first_name": ("like", f"{performance.MARK} %")}))
		self.assertEqual(frappe.db.count(RULE_DOCTYPE), len(self.rules) + 1)

	def test_failed_measurement_keeps_older_rules_and_records(self):
		with patch.object(performance, "measure_endpoints", side_effect=RuntimeError("stopped on purpose")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_seeding_keeps_older_rules_and_records(self):
		with patch.object(frappe.db, "bulk_insert", side_effect=RuntimeError("stopped on purpose")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_finished_measurement_removes_only_what_it_made(self):
		quick = [{"kind": "read", "endpoint": "none", "calls": 50, "statuses": [200]}]
		with (
			patch.object(performance, "measure_endpoints", return_value=quick),
			patch.object(performance, "measure_rule_cost", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			report = performance.measure(**SMALL)

		self.assertEqual(report["records"], SMALL["records"])
		self.assert_site_as_before()
