"""The hand-started measurement must leave a site as it found it (review of 9c7d6d8)."""

from unittest.mock import patch

import frappe

from platform_core.erisim import field_level
from platform_core.erisim.tests import performance
from platform_core.erisim.tests.base import (
	DOCTYPE,
	FREE_DOCTYPE,
	ROLE_HR,
	ROLE_MANAGER,
	RULE_DOCTYPE,
	ErisimTestCase,
)

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
		# A level permission an administrator gave before the measurement: read and write at level 1.
		field_level.set_level_access(DOCTYPE, ROLE_MANAGER, 1, True, True)
		self.old_permissions = self.permission_rows()
		self.assertIn((ROLE_MANAGER, 1, 1, 1), self.old_permissions)
		# Committed on purpose: the measurement commits and its requests use another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		self.addCleanup(self.remove_old_rule)

	def permission_rows(self) -> set[tuple]:
		rows = frappe.get_all(
			"Custom DocPerm",
			filters={"parent": DOCTYPE},
			fields=["role", "permlevel", "read", "write"],
			limit=0,
		)
		return {(row.role, row.permlevel, row.read, row.write) for row in rows}

	def measured_type(self) -> str:
		"""The type the measurement writes to. It must not be a type that holds other data."""
		return getattr(performance, "MEASURE_DOCTYPE", DOCTYPE)

	def remove_old_rule(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("Custom DocPerm", {"parent": DOCTYPE})
		frappe.clear_cache(doctype=DOCTYPE)
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
		self.assertEqual(self.permission_rows(), self.old_permissions)
		self.assertNotEqual(self.measured_type(), DOCTYPE)
		self.assertFalse(frappe.db.count(self.measured_type()))
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": self.measured_type()}))

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

	def test_real_measurement_keeps_an_existing_level_permission(self):
		"""Review finding: the level access case must not touch a permission that was there before."""
		with (
			patch.object(performance, "measure_rule_cost", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			report = performance.measure(**SMALL)

		self.assertEqual({row["result"] for row in report["endpoints"]}, {"pass"})
		self.assert_site_as_before()

	def test_stop_right_after_a_created_record_leaves_nothing_behind(self):
		"""Review finding: a record made by a request must be removed when the run stops early."""
		real_send = performance.send
		created = []

		def stop_after_first_create(client, method, path, **arguments):
			response = real_send(client, method, path, **arguments)
			if method == "POST" and "/api/v2/document/" in path and response.status_code == 200:
				created.append(response.json["data"]["name"])
				raise RuntimeError("stopped on purpose")
			return response

		with patch.object(performance, "send", stop_after_first_create):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assertEqual(len(created), 1)
		self.assert_site_as_before()
