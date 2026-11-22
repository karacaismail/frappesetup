"""The hand-started measurement must leave a site exactly as it found it.

The measurement works on a document type, roles, users, employees and rules of its own, made
for one run and removed again. These tests take a picture of the tables that hold permissions
and people before the run and compare it with the tables afterwards, also when the run stops
half way. The picture includes things an administrator set up before: a rule, a level
permission, a user permission, and a test type without the portal role (an older site).
"""

from unittest.mock import patch

import frappe

from platform_core.erisim import field_level
from platform_core.erisim.tests import base, performance
from platform_core.erisim.tests.base import (
	COMPANY,
	DOCTYPE,
	EMPLOYEE_1,
	FREE_DOCTYPE,
	ROLE_HR,
	ROLE_MANAGER,
	ROLE_PORTAL,
	RULE_DOCTYPE,
	ErisimTestCase,
)

SMALL = {"calls": 50, "employees": 12, "records": 40}
# Every table a measurement could leave a trace in: permissions, people, rules and types.
WATCHED = (
	"User Permission",
	"DocPerm",
	"Custom DocPerm",
	"Property Setter",
	"Has Role",
	"Role",
	"User",
	"Employee",
	"Contact",
	"Deleted Document",
	"Version",
	"Comment",
	"Activity Log",
	"Access Log",
	"Notification Settings",
	"Company",
	"Gender",
	"DocType",
	"DocShare",
	RULE_DOCTYPE,
	DOCTYPE,
	FREE_DOCTYPE,
)


def picture() -> dict[str, list]:
	"""Name and last change of every row in the watched tables."""
	frappe.db.rollback()
	return {
		table: sorted(
			(str(row.name), str(row.modified))
			for row in frappe.get_all(table, fields=["name", "modified"], limit=0)
		)
		for table in WATCHED
	}


class TestMeasurementLeavesTheSiteAsItWas(ErisimTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self.restore_site)
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
		).insert()
		# A level permission an administrator gave before: read and write at level 1.
		field_level.set_level_access(DOCTYPE, ROLE_MANAGER, 1, True, True)
		# A user permission an administrator gave to one of the made-up users.
		frappe.get_doc(
			{"doctype": "User Permission", "user": EMPLOYEE_1, "allow": "Company", "for_value": COMPANY}
		).insert()
		# An older site: the test type has no row for the portal role yet.
		frappe.db.delete("DocPerm", {"parent": DOCTYPE, "role": ROLE_PORTAL})
		frappe.db.delete("Custom DocPerm", {"parent": DOCTYPE, "role": ROLE_PORTAL})
		frappe.clear_cache(doctype=DOCTYPE)
		# Committed on purpose: the measurement commits and its requests use another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		self.before = picture()
		self.assertTrue(self.before["User Permission"])
		self.assertTrue(self.before["Custom DocPerm"])

	def restore_site(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("User Permission", {"user": EMPLOYEE_1})
		frappe.db.delete("Custom DocPerm", {"parent": DOCTYPE})
		frappe.db.delete(RULE_DOCTYPE, {"document_type": FREE_DOCTYPE})
		frappe.clear_cache(doctype=DOCTYPE)
		base.ensure_portal_permission()
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	def assert_site_as_before(self) -> None:
		after = picture()
		for table in WATCHED:
			with self.subTest(table=table):
				self.assertEqual(after[table], self.before[table])
		leftover = frappe.db.sql_list("show tables like %s", (f"tab{performance.MARK}%",))
		self.assertEqual(leftover, [])

	def test_finished_measurement_changes_no_watched_table(self):
		"""The whole run with real requests: every endpoint is called."""
		with (
			patch.object(performance, "measure_rule_cost", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			report = performance.measure(**SMALL)

		self.assertEqual({row["result"] for row in report["endpoints"]}, {"pass"})
		self.assertEqual(report["records"], SMALL["records"])
		self.assertEqual(report["employees"], SMALL["employees"])
		self.assert_site_as_before()

	def test_measurement_with_the_rule_cost_changes_no_watched_table(self):
		with (
			patch.object(performance, "measure_endpoints", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			report = performance.measure(**SMALL)

		self.assertEqual(len(report["rule_cost"]), 6)
		self.assert_site_as_before()

	def test_failure_while_measuring_changes_no_watched_table(self):
		with patch.object(performance, "measure_endpoints", side_effect=RuntimeError("stopped on purpose")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_seeding_changes_no_watched_table(self):
		with patch.object(frappe.db, "bulk_insert", side_effect=RuntimeError("stopped on purpose")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_making_the_people_changes_no_watched_table(self):
		with patch.object(performance, "make_rules", side_effect=RuntimeError("stopped on purpose")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_stop_right_after_a_created_record_changes_no_watched_table(self):
		"""A record made by a request must be removed when the run stops early."""
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

	def test_measurement_does_not_call_the_shared_test_setup(self):
		"""The shared setup deletes user permissions and adds rows to the test types."""
		with (
			patch.object(base, "ensure_fixtures", side_effect=AssertionError("shared setup was called")),
			patch.object(performance, "measure_endpoints", return_value=[]),
			patch.object(performance, "measure_rule_cost", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			performance.measure(**SMALL)
