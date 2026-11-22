"""The hand-started measurement follows rule O-35 of the project record.

- It runs only on a site whose name starts with `perf-` and ends with `.localhost`, and only
  when the site configuration has `allow_performance_fixture` set to 1.
- It stops before it creates anything when a background job is waiting. It never runs the
  queue.
- It deletes only what it created, chosen by document type and name together.

Two kinds of tests live here.

`TestMeasurementLogic` checks the decisions of the command with made-up data. It writes nothing
to the database and runs on every site.

The other classes run the command for real and compare the tables before and after. They
change the database, so they follow the same rule as the command: they run only on a
`perf-*.localhost` site with the fixture switched on, and are skipped everywhere else with the
reason below. They never run the shared queue and never empty it: the measurement is shown a
queue of its own, and the queue test removes only the one job it added.
"""

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils.background_jobs import get_redis_conn
from rq import Queue

from platform_core.access import field_level
from platform_core.access.tests import base, performance
from platform_core.access.tests.base import (
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
# The limits of rule O-31 in the project record (`backend/PROJE-KAYDI.md`): p95 of a read
# endpoint at most 500 ms, p95 of a write endpoint at most 1 second. They are written here on
# purpose and not taken from the measurement code, so a changed limit in that code shows.
O31_READ_LIMIT_MS = 500
O31_WRITE_LIMIT_MS = 1000
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


SKIP_REASON = (
	"These tests change the database. They run only on a perf-*.localhost site "
	"with allow_performance_fixture set to 1 (O-35)."
)


def require_perf_site() -> None:
	"""Skip a class that writes to the database unless the site is a measuring site."""
	if not performance.site_allowed(frappe.local.site, frappe.conf):
		raise unittest.SkipTest(SKIP_REASON)


@contextmanager
def with_own_queue():
	"""Show the measurement the tests' own queue instead of the shared one."""
	with patch.object(performance, "get_queues", return_value=[own_queue()]):
		yield


@contextmanager
def pretend_site(name: str = PERF_SITE, flag=1, waiting: int = 0):
	"""For the logic tests: a site name, a flag and a queue length, all made up."""
	queue = MagicMock()
	queue.count = waiting
	with (
		patch.object(performance, "site_name", return_value=name),
		patch.object(performance, "get_queues", return_value=[queue]),
		patch.dict(frappe.conf, clear=False),
	):
		frappe.conf.pop("allow_performance_fixture", None)
		if flag is not None:
			frappe.conf["allow_performance_fixture"] = flag
		yield queue


class TestMeasurementLogic(unittest.TestCase):
	"""The decisions of the command, with made-up data. Nothing is written to the database."""

	def setUp(self):
		# The three steps that would touch the database are replaced for every test here.
		self.seed = self.replace("seed")
		self.clean = self.replace("clean")
		self.cases = self.replace("endpoint_cases", return_value=[])
		self.rule_cost = self.replace("measure_rule_cost", return_value=[])
		self.replace("as_markdown", return_value="")

	def replace(self, name: str, **arguments) -> MagicMock:
		patcher = patch.object(performance, name, **arguments)
		self.addCleanup(patcher.stop)
		return patcher.start()

	def fill_sample(self, sample, employees, records) -> None:
		sample.update(employees=employees, records=records, own="record", employee_name="employee")

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

	def test_wrong_site_stops_before_anything_is_created(self):
		with pretend_site(name="test-platform-core.localhost"):
			self.assertRaises(performance.NotAllowedHere, performance.measure, **SMALL)

		self.seed.assert_not_called()
		self.clean.assert_not_called()

	def test_missing_flag_stops_before_anything_is_created(self):
		for flag in (None, 0):
			with self.subTest(flag=flag), pretend_site(flag=flag):
				self.assertRaises(performance.NotAllowedHere, performance.measure, **SMALL)

		self.seed.assert_not_called()
		self.clean.assert_not_called()

	def test_waiting_job_stops_before_anything_is_created_and_is_not_run(self):
		with pretend_site(waiting=3) as queue:
			self.assertRaises(performance.QueueNotEmpty, performance.measure, **SMALL)

		self.seed.assert_not_called()
		self.clean.assert_not_called()
		# The queue was only looked at: nothing was run, emptied or added.
		self.assertEqual(queue.mock_calls, [])

	def test_measurement_counts_every_queue_of_the_bench(self):
		queues = [SimpleNamespace(count=2), SimpleNamespace(count=0), SimpleNamespace(count=5)]
		with patch.object(performance, "get_queues", return_value=queues):
			self.assertEqual(performance.waiting_jobs(), 7)

	def test_clean_up_runs_when_the_run_finishes(self):
		self.seed.side_effect = self.fill_sample
		with pretend_site():
			report = performance.measure(**SMALL)

		self.assertEqual((report["employees"], report["records"]), (SMALL["employees"], SMALL["records"]))
		self.clean.assert_called_once()
		self.assertEqual(self.clean.call_args.args[0]["run"], self.seed.call_args.args[0]["run"])

	def test_clean_up_runs_when_seeding_fails(self):
		self.seed.side_effect = RuntimeError("stopped on purpose")
		with pretend_site():
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.clean.assert_called_once()

	def test_clean_up_runs_when_a_request_fails(self):
		self.seed.side_effect = self.fill_sample
		self.cases.side_effect = RuntimeError("stopped on purpose")
		with pretend_site():
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.clean.assert_called_once()

	def test_every_endpoint_is_called_at_least_fifty_times(self):
		self.seed.side_effect = self.fill_sample
		calls = []

		def request(number):
			calls.append(number)
			return SimpleNamespace(status_code=200)

		self.cases.return_value = [("read", "Made-up read", request)]
		with pretend_site():
			report = performance.measure(calls=3, employees=1, records=1)

		# One warm-up call and fifty timed calls, also when fewer were asked for.
		self.assertEqual(len(calls), 51)
		self.assertEqual(report["endpoints"][0]["calls"], 50)
		self.assertEqual(report["endpoints"][0]["result"], "pass")

	def test_result_fails_on_a_slow_endpoint_and_on_an_error_answer(self):
		self.seed.side_effect = self.fill_sample
		ok = lambda _number: SimpleNamespace(status_code=200)  # noqa: E731
		error = lambda _number: SimpleNamespace(status_code=500)  # noqa: E731
		deleted = lambda _number: SimpleNamespace(status_code=202)  # noqa: E731
		self.cases.return_value = [
			("read", "fast read", ok),
			("read", "slow read", ok),
			("write", "fast write", ok),
			("write", "slow write", ok),
			("write", "delete", deleted),
			("read", "error", error),
		]
		times = {
			"fast read": O31_READ_LIMIT_MS,
			"slow read": O31_READ_LIMIT_MS + 1,
			"fast write": O31_WRITE_LIMIT_MS,
			"slow write": O31_WRITE_LIMIT_MS + 1,
			"delete": 5,
			"error": 5,
		}
		labels = iter(times)

		def timed(calls, request):
			return [float(times[next(labels)])] * calls, {request(0).status_code}

		with pretend_site(), patch.object(performance, "timed", timed):
			report = performance.measure(**SMALL)

		results = {row["endpoint"]: row["result"] for row in report["endpoints"]}
		self.assertEqual(
			results,
			{
				"fast read": "pass",
				"slow read": "fail",
				"fast write": "pass",
				"slow write": "fail",
				"delete": "pass",
				"error": "fail",
			},
		)
		# The report states the limit it judged by. It must be the limit of rule O-31.
		limits = {row["kind"]: row["limit_ms"] for row in report["endpoints"]}
		self.assertEqual(limits, {"read": O31_READ_LIMIT_MS, "write": O31_WRITE_LIMIT_MS})

	def test_the_limits_are_those_of_rule_o31(self):
		self.assertEqual(performance.READ_LIMIT_MS, O31_READ_LIMIT_MS)
		self.assertEqual(performance.WRITE_LIMIT_MS, O31_WRITE_LIMIT_MS)

	def test_every_name_of_a_run_carries_its_mark(self):
		first, second = performance.new_sample(), performance.new_sample()

		self.assertNotEqual(first["run"], second["run"])
		names = [first["doctype"], first["company"], first["gender"], *first["roles"].values()]
		for name in names:
			with self.subTest(name=name):
				self.assertTrue(name.startswith(f"{performance.MARK} {first['run']} "))
		for email in first["users"].values():
			with self.subTest(email=email):
				self.assertTrue(email.startswith(f"ar.measure.{first['run']}."))
				self.assertTrue(email.endswith("@example.test"))

	def test_log_rows_are_chosen_by_type_and_name_together(self):
		"""Rule O-35. The searches of the clean-up are recorded; none of them is run."""
		# Pure input: this test also runs after Frappe has released its site/database context.
		sample = {
			"started": "2026-11-22 12:00:00",
			"doctype": "Measurement Request",
			"users": {
				"manager": "measurement.manager@example.test",
				"employee": "measurement.employee@example.test",
			},
		}
		made = [("PLT Access Rule", "AR-00001"), ("Employee", "HR-EMP-00001"), ("Role", "A role")]
		searches = []

		def record(table, filters=None, **_arguments):
			searches.append((table, filters))
			return []

		# Replace the module attribute, not a method on the unbound LocalProxy.
		database = SimpleNamespace(delete=MagicMock())
		with patch.object(frappe, "get_all", record), patch.object(frappe, "db", database):
			performance.clean_traces(sample, made)

		database.delete.assert_not_called()
		self.assertGreater(len(searches), 10)
		users = set(sample["users"].values())
		# Frappe 16 DocType fields, independent of the cleanup implementation.
		# O-35 requires the document type AND name to select the run's records.
		fields = {
			"Deleted Document": ("deleted_doctype", "deleted_name"),
			"Version": ("ref_doctype", "docname"),
			"Comment": ("reference_doctype", "reference_name"),
			"Activity Log": ("reference_doctype", "reference_name"),
		}
		for table, filters in searches:
			with self.subTest(table=table, filters=sorted(filters)):
				# Never older than the run: a name can be given out again after a delete.
				self.assertEqual(filters["creation"], (">=", sample["started"]))
				by_user = set(filters.get("owner", filters.get("user", ("in", [])))[1]) == users
				kind_field, name_field = fields.get(table, (None, None))
				own_type = filters.get(kind_field) == sample["doctype"]
				pair = kind_field in filters and (name_field in filters or "subject" in filters)
				if "subject" in filters:
					pair = "reference_doctype" in filters
				self.assertTrue(by_user or own_type or pair)
				if name_field in filters:
					# A name is never searched without its type.
					self.assertIn(filters[kind_field], {kind for kind, _name in made})
					expected_names = [name for kind, name in made if kind == filters[kind_field]]
					self.assertEqual(filters[name_field], ("in", expected_names))


class TestMeasurementLeavesTheSiteAsItWas(ErisimTestCase):
	"""Runs the command for real. Only on a measuring site (O-35); skipped everywhere else."""

	RUN_WAITING_JOBS = False

	@classmethod
	def setUpClass(cls):
		require_perf_site()
		super().setUpClass()

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
			with_own_queue(),
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
			with_own_queue(),
			patch.object(performance, "measure_endpoints", return_value=[]),
			patch.object(performance, "as_markdown", return_value=""),
		):
			report = performance.measure(**SMALL)

		self.assertEqual(len(report["rule_cost"]), 6)
		self.assert_site_as_before()

	def test_failure_while_measuring_changes_no_watched_table(self):
		stop = patch.object(performance, "measure_endpoints", side_effect=RuntimeError("stopped on purpose"))
		with with_own_queue(), stop:
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_seeding_changes_no_watched_table(self):
		with with_own_queue(), patch.object(frappe.db, "bulk_insert", side_effect=RuntimeError("stopped")):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assert_site_as_before()

	def test_failure_while_making_the_rules_changes_no_watched_table(self):
		with with_own_queue(), patch.object(performance, "make_rules", side_effect=RuntimeError("stopped")):
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

		with with_own_queue(), patch.object(performance, "send", stop_after_first_create):
			self.assertRaises(RuntimeError, performance.measure, **SMALL)

		self.assertEqual(len(created), 1)
		self.assert_site_as_before()

	def test_measurement_does_not_call_the_shared_test_setup(self):
		"""The shared setup deletes user permissions and adds rows to the test types."""
		with (
			with_own_queue(),
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

		with with_own_queue():
			self.assertRaises(performance.QueueNotEmpty, performance.measure, **SMALL)

		self.assertEqual(queue.count, waiting)
		self.assertIn(job.id, queue.job_ids)
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
			with_own_queue(),
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

	@classmethod
	def setUpClass(cls):
		require_perf_site()
		super().setUpClass()

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
