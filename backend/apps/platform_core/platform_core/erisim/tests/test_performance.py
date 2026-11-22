"""The hand-started measurement follows rule O-35 of the project record.

- It runs only on a site whose name starts with `perf-` and ends with `.localhost`, and only
  when the site configuration has `allow_performance_fixture` set to 1.
- It stops before it creates anything when a background job is waiting. It never runs the
  queue.
- It deletes only what it created, chosen by document type and name together.

The tests run on the shared test site, so the site name is patched where the run itself is
under test. They never run the shared queue and never empty it: the measurement is shown a
queue of its own, made for these tests, and the queue test removes only the one job it added. They take a picture of the tables that hold permissions, people, rules and logs
before the run and compare it with the tables afterwards, also when the run stops half way.

The set-up of these tests changes a few rows of the shared site. It keeps a copy of every row
it removes and puts the copies back, and it deletes only the rows it added itself.
"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.utils.background_jobs import get_redis_conn
from rq import Queue

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
# The rows the set-up of these tests may add, change or delete. It keeps all of them, with every
# field, and puts them back exactly.
SCOPE = {
	"DocPerm": {"parent": DOCTYPE},
	"Custom DocPerm": {"parent": DOCTYPE},
	"User Permission": {"user": EMPLOYEE_1},
}


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


def own_queue() -> Queue:
	"""A queue only these tests use. No worker listens to it and nothing else puts jobs in it."""
	return Queue("ar-measure-tests", connection=get_redis_conn())


@contextmanager
def on_a_perf_site(name: str = PERF_SITE, flag=1):
	"""Let the measurement see a site it may run on, and the tests' own queue instead of the shared one.

	The data still goes to the test site.
	"""
	with (
		patch.object(performance, "site_name", return_value=name),
		patch.object(performance, "get_queues", return_value=[own_queue()]),
		patch.dict(frappe.conf, clear=False),
	):
		frappe.conf.pop("allow_performance_fixture", None)
		if flag is not None:
			frappe.conf["allow_performance_fixture"] = flag
		yield


class TestWhereTheMeasurementMayRun(ErisimTestCase):
	"""Rule O-35, first part: the site."""

	RUN_WAITING_JOBS = False

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
		before = picture()
		with patch.dict(frappe.conf, {"allow_performance_fixture": 1}):
			self.assertRaises(performance.NotAllowedHere, performance.measure, **SMALL)

		self.assertEqual(picture(), before)

	def test_measurement_refuses_a_perf_site_without_the_flag(self):
		before = picture()
		with on_a_perf_site(flag=None):
			self.assertRaises(performance.NotAllowedHere, performance.measure, **SMALL)

		self.assertEqual(picture(), before)


class TestMeasurementLeavesTheSiteAsItWas(ErisimTestCase):
	RUN_WAITING_JOBS = False

	def setUp(self):
		super().setUp()
		# Every row the set-up below may add, change or delete, with all its fields.
		self.kept = {table: self.rows(table, filters) for table, filters in SCOPE.items()}
		self.added_rules: list[str] = []
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
		self.added_rules.append(rule.name)
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

	@staticmethod
	def rows(table: str, filters: dict) -> dict[str, dict]:
		"""Every row in the scope, by name, with every column."""
		return {row.name: row for row in frappe.get_all(table, filters=filters, fields=["*"], limit=0)}

	def restore_site(self) -> None:
		"""Make the rows in the scope exactly what they were before the set-up.

		A row the set-up added is deleted. A row it deleted is written again. A row it changed,
		for example a level permission whose write access it switched on, gets its old values
		back. Rows outside the scope are never touched.
		"""
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in self.added_rules:
			frappe.db.delete(RULE_DOCTYPE, {"name": name})
		for table, filters in SCOPE.items():
			now_there = self.rows(table, filters)
			for name, row in now_there.items():
				if name not in self.kept[table] or row != self.kept[table][name]:
					frappe.db.delete(table, {"name": name})
			for name, row in self.kept[table].items():
				if name not in now_there or now_there[name] != row:
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
		queue = own_queue()
		job = queue.enqueue("frappe.ping")
		# Only the job this test added is removed. The queue is never run and never emptied.
		self.addCleanup(job.delete)
		waiting = queue.count
		self.assertGreaterEqual(waiting, 1)

		with on_a_perf_site():
			self.assertRaises(performance.QueueNotEmpty, performance.measure, **SMALL)

		self.assertEqual(queue.count, waiting)
		self.assertIn(job.id, queue.job_ids)
		self.assert_site_as_before()

	def test_measurement_counts_the_shared_queue_when_nothing_is_patched(self):
		"""Outside these tests the measurement looks at the real queues of the bench."""
		from frappe.utils.background_jobs import get_queues

		self.assertEqual(performance.waiting_jobs(), sum(queue.count for queue in get_queues()))

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

	RUN_WAITING_JOBS = False

	def test_rows_from_before_the_set_up_survive_it(self):
		# A custom permission of the portal role and a user permission, both from before.
		copies = set(frappe.get_all("Custom DocPerm", filters={"parent": DOCTYPE}, pluck="name", limit=0))
		field_level.set_level_access(DOCTYPE, ROLE_PORTAL, 1, True, False)
		# The manager may read level 1 and may not write it. The set-up gives the manager write
		# access for its own purpose; afterwards this row must be exactly as it is now.
		field_level.set_level_access(DOCTYPE, ROLE_MANAGER, 1, True, False)
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
		manager_row = {"parent": DOCTYPE, "role": ROLE_MANAGER, "permlevel": 1}
		self.assertEqual(frappe.db.get_value("Custom DocPerm", manager_row, ["read", "write"]), (1, 0))
		# The set-up and the clean-up must not run the shared queue either (O-35).
		with patch.object(base, "run_queued_jobs", side_effect=AssertionError("the shared queue was run")):
			inner.setUp()
			inner.doCleanups()
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Custom DocPerm", manager_row, ["read", "write"]), (1, 0))

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
