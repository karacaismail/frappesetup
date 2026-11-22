"""The hand-started measurement follows rule O-35 of the project record.

- It runs only on a site whose name starts with `perf-` and ends with `.localhost`, and only
  when the site configuration has `allow_performance_fixture` set to 1.
- It stops before it creates anything when a background job is waiting. It never runs the
  queue.
- It deletes only what it created, chosen by document type and name together.

The tests run on the shared test site, so the site name is patched where the run itself is
under test. They take a picture of the tables that hold permissions, people, rules and logs
before the run and compare it with the tables afterwards, also when the run stops half way.

The set-up of these tests changes a few rows of the shared site. It keeps a copy of every row
it removes and puts the copies back, and it deletes only the rows it added itself.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.utils.background_jobs import get_queues

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
PERF_SITE = "perf-access.localhost"
# Every table a measurement could leave a trace in: permissions, people, rules, types and logs.
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
# The permission tables whose rows the set-up of these tests removes and must put back.
RESTORED = ("DocPerm", "Custom DocPerm", "User Permission")


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


def picture_of(table: str) -> list[tuple]:
	"""Every column of every row, so a row that was deleted and written again differently shows."""
	frappe.db.rollback()
	rows = frappe.get_all(table, fields=["*"], order_by="name asc", limit=0)
	return [tuple(str(row[key]) for key in sorted(row)) for row in rows]


def waiting_jobs() -> int:
	return sum(queue.count for queue in get_queues())


@contextmanager
def on_a_perf_site(name: str = PERF_SITE, flag=1):
	"""Let the measurement see a site it may run on. The data still goes to the test site."""
	with patch.object(performance, "site_name", return_value=name), patch.dict(frappe.conf, clear=False):
		frappe.conf.pop("allow_performance_fixture", None)
		if flag is not None:
			frappe.conf["allow_performance_fixture"] = flag
		yield


class TestWhereTheMeasurementMayRun(ErisimTestCase):
	"""Rule O-35, first part: the site."""

	def test_site_names(self):
		allowed = ("perf-access.localhost", "perf-1.localhost")
		refused = (
			"test-platform-core.localhost",
			"perf.localhost",
			"perf-.localhost",
			"myperf-a.localhost",
			"perf-a.example.com",
			"perf-a.localhost.example.com",
			"PERF-a.localhost",
			"",
		)
		for name in allowed:
			with self.subTest(name=name):
				self.assertTrue(performance.site_allowed(name, {"allow_performance_fixture": 1}))
		for name in refused:
			with self.subTest(name=name):
				self.assertFalse(performance.site_allowed(name, {"allow_performance_fixture": 1}))

	def test_site_flag(self):
		for value in (None, 0, "0", "", False):
			with self.subTest(value=value):
				self.assertFalse(performance.site_allowed(PERF_SITE, {"allow_performance_fixture": value}))
		self.assertFalse(performance.site_allowed(PERF_SITE, {}))
		self.assertFalse(performance.site_allowed(PERF_SITE, {"allow_tests": 1}))
		self.assertTrue(performance.site_allowed(PERF_SITE, {"allow_performance_fixture": "1"}))

	def test_measurement_refuses_the_test_site_and_creates_nothing(self):
		base.run_queued_jobs(room=1)
		before = picture()
		with patch.dict(frappe.conf, {"allow_performance_fixture": 1}):
			self.assertRaises(performance.NotAllowedHere, performance.measure, **SMALL)

		self.assertEqual(picture(), before)

	def test_measurement_refuses_a_perf_site_without_the_flag(self):
		base.run_queued_jobs(room=1)
		before = picture()
		with on_a_perf_site(flag=None):
			self.assertRaises(performance.NotAllowedHere, performance.measure, **SMALL)

		self.assertEqual(picture(), before)


class TestMeasurementLeavesTheSiteAsItWas(ErisimTestCase):
	def setUp(self):
		super().setUp()
		# These tests need an empty queue. The shared test site has no worker, so run what waits.
		base.run_queued_jobs(room=1)
		self.removed: dict[str, list[dict]] = {table: [] for table in RESTORED}
		self.added: list[tuple[str, str]] = []
		self.addCleanup(self.restore_site)
		rule = frappe.get_doc(
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
		self.added.append((RULE_DOCTYPE, rule.name))
		# A level permission an administrator gave before: read and write at level 1.
		copies = set(frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, pluck="name", limit=0))
		field_level.set_level_access(DOCTYPE, ROLE_MANAGER, 1, True, True)
		now_there = frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, pluck="name", limit=0)
		self.added += [("Custom DocPerm", name) for name in now_there if name not in copies]
		# A user permission an administrator gave to one of the made-up users.
		permission = frappe.get_doc(
			{"doctype": "User Permission", "user": EMPLOYEE_1, "allow": "Company", "for_value": COMPANY}
		).insert()
		self.added.append(("User Permission", permission.name))
		# An older site: the test type has no row for the portal role yet.
		self.remove_and_keep("DocPerm", {"parent": DOCTYPE, "role": ROLE_PORTAL})
		self.remove_and_keep("Custom DocPerm", {"parent": DOCTYPE, "role": ROLE_PORTAL})
		frappe.clear_cache(doctype=DOCTYPE)
		# Committed on purpose: the measurement commits and its requests use another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		self.before = picture()
		self.assertTrue(self.before["User Permission"])
		self.assertTrue(self.before["Custom DocPerm"])

	def remove_and_keep(self, table: str, filters: dict) -> None:
		"""Delete rows for the test. A row from before the set-up is copied first, to be put back."""
		for name in frappe.get_all(table, filters=filters, pluck="name", limit=0):
			if (table, name) in self.added:
				self.added.remove((table, name))
			else:
				self.removed[table].append(frappe.db.get_value(table, name, "*", as_dict=True))
			frappe.db.delete(table, {"name": name})

	def restore_site(self) -> None:
		"""Delete only what the set-up added and put back every row it removed, unchanged."""
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for table, name in self.added:
			frappe.db.delete(table, {"name": name})
		for table, rows in self.removed.items():
			for row in rows:
				if not frappe.db.exists(table, row["name"]):
					frappe.get_doc({"doctype": table, **row}).db_insert()
		frappe.clear_cache(doctype=DOCTYPE)
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
			on_a_perf_site(),
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
			on_a_perf_site(),
			patch.object(performance, "measure_endpoints", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			report = performance.measure(**SMALL)

		self.assertEqual(len(report["rule_cost"]), 6)
		self.assert_site_as_before()

	def test_failure_while_measuring_changes_no_watched_table(self):
		stop = patch.object(performance, "measure_endpoints", side_effect=RuntimeError("stopped on purpose"))
		with on_a_perf_site(), stop:
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_seeding_changes_no_watched_table(self):
		with on_a_perf_site(), patch.object(frappe.db, "bulk_insert", side_effect=RuntimeError("stopped")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_making_the_rules_changes_no_watched_table(self):
		with on_a_perf_site(), patch.object(performance, "make_rules", side_effect=RuntimeError("stopped")):
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

		with on_a_perf_site(), patch.object(performance, "send", stop_after_first_create):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assertEqual(len(created), 1)
		self.assert_site_as_before()

	def test_measurement_does_not_call_the_shared_test_setup(self):
		"""The shared setup deletes user permissions and adds rows to the test types."""
		with (
			on_a_perf_site(),
			patch.object(base, "ensure_fixtures", side_effect=AssertionError("shared setup was called")),
			patch.object(base, "run_queued_jobs", side_effect=AssertionError("the queue was run")),
			patch.object(performance, "measure_endpoints", return_value=[]),
			patch.object(performance, "measure_rule_cost", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			performance.measure(**SMALL)

	def test_waiting_job_stops_the_measurement_and_stays_in_the_queue(self):
		"""Rule O-35: a job of other work waits. Nothing is created and the job is not run."""
		frappe.enqueue("frappe.ping", queue="default")
		self.addCleanup(base.run_queued_jobs, 1)
		waiting = waiting_jobs()
		self.assertGreaterEqual(waiting, 1)

		with on_a_perf_site():
			self.assertRaises(performance.QueueNotEmpty, performance.measure, **SMALL)

		self.assertEqual(waiting_jobs(), waiting)
		self.assert_site_as_before()

	def test_log_rows_of_another_type_with_the_same_name_are_kept(self):
		"""Rule O-35: the clean-up chooses by type and name together.

		While the run goes on, a record of another type gets log rows. That record happens to
		have the same name as a rule of the run.
		"""
		logs: list[tuple[str, str]] = []

		def write_logs_of_another_type(sample, _calls):
			same_name = sample["rules"][0]
			link = {"reference_doctype": FREE_DOCTYPE, "reference_name": same_name}
			rows = (
				{"doctype": "Comment", "comment_type": "Comment", "content": "Kept", **link},
				{
					"doctype": "Comment",
					"comment_type": "Deleted",
					"subject": f"{FREE_DOCTYPE} {same_name}",
					**link,
				},
				{"doctype": "Version", "ref_doctype": FREE_DOCTYPE, "docname": same_name, "data": "{}"},
				{"doctype": "Deleted Document", "deleted_doctype": FREE_DOCTYPE, "deleted_name": same_name},
			)
			for row in rows:
				# Written straight to the table: the record these rows speak of is made up.
				doc = frappe.get_doc(row)
				doc.name = frappe.generate_hash(length=10)
				doc.db_insert()
				logs.append((doc.doctype, doc.name))
			# Committed on purpose: the clean-up rolls back first.
			frappe.db.commit()  # nosemgrep: frappe-request-commit
			return []

		self.addCleanup(lambda: [frappe.db.delete(table, {"name": name}) for table, name in logs])
		with (
			on_a_perf_site(),
			patch.object(performance, "measure_endpoints", write_logs_of_another_type),
			patch.object(performance, "measure_rule_cost", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			performance.measure(**SMALL)

		frappe.db.rollback()
		self.assertEqual(len(logs), 4)
		for table, name in logs:
			with self.subTest(table=table):
				self.assertTrue(frappe.db.exists(table, name))


class TestTheSetUpPutsBackWhatItChanged(ErisimTestCase):
	"""Review finding: the set-up above must not lose a permission that was there before it."""

	def test_rows_from_before_the_set_up_survive_it(self):
		# A custom permission of the portal role and a user permission, both from before.
		copies = set(frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, pluck="name", limit=0))
		field_level.set_level_access(DOCTYPE, ROLE_PORTAL, 1, True, False)
		now_there = frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, pluck="name", limit=0)
		made = [name for name in now_there if name not in copies]
		earlier = frappe.get_doc(
			{"doctype": "User Permission", "user": EMPLOYEE_1, "allow": "Gender", "for_value": base.GENDER}
		).insert()
		# Committed on purpose: the inner test case rolls back and commits on its own.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		self.addCleanup(self.remove_earlier_rows, earlier.name, made)
		tables = ("DocPerm", "Custom DocPerm", "User Permission", RULE_DOCTYPE)
		before = {table: picture_of(table) for table in tables}
		self.assertTrue(any(earlier.name in row for row in before["User Permission"]))

		inner = TestMeasurementLeavesTheSiteAsItWas("test_measurement_does_not_call_the_shared_test_setup")
		inner.records, inner.rules, inner.site = self.records, self.rules, self.site
		inner.setUp()
		inner.doCleanups()

		for table in tables:
			with self.subTest(table=table):
				self.assertEqual(picture_of(table), before[table])

	def remove_earlier_rows(self, user_permission: str, custom_permissions: list[str]) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("User Permission", {"name": user_permission})
		if custom_permissions:
			frappe.db.delete("Custom DocPerm", {"name": ("in", custom_permissions)})
		frappe.clear_cache(doctype=DOCTYPE)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
