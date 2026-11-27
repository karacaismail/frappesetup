"""Reject endpoint and home page summary (AJA-1165). Written before the code.

The new home page shows four parts: pending approvals, problem records, recent changes and
summary numbers. `hrms_tr.api.get_home_summary` returns them. `hrms_tr.api.reject_leave`
rejects an open leave with the same rules as `approve_leave`.

The rule tests at the top need no site. The request tests go through the WSGI application of
Frappe with a real session and need a test site with HRMS TR and platform_core installed:
`backend/dev/bin/test hrms_tr --module hrms_tr.tests.test_home_summary`.
All people, companies and records are made up.
"""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

try:
	import frappe
	from frappe.tests import IntegrationTestCase
	from frappe.tests.test_api import make_request
	from frappe.utils import (
		add_days,
		add_months,
		get_first_day,
		get_test_client,
		getdate,
		now_datetime,
		today,
	)
	from frappe.utils.password import update_password
except ImportError:  # Outside a bench the tests are skipped.
	frappe = None
	IntegrationTestCase = unittest.TestCase
if frappe is not None:
	# Not inside the guard: a missing module must fail, not skip.
	from hrms_tr import home_summary

DOCTYPE = "Leave Application"
REJECT = "/api/method/hrms_tr.api.reject_leave"
SUMMARY = "/api/method/hrms_tr.api.get_home_summary"
# Required fields of each part, as `contracts/hrms_tr.openapi.yaml` states them.
# `backend/dev/hrms/test_contract.py` checks that the contract says the same.
SUMMARY_PARTS = {"pending_approvals", "problems", "recent_changes", "counts"}
PENDING_FIELDS = {
	"name",
	"version",
	"employee_name",
	"leave_type",
	"from_date",
	"to_date",
	"total_leave_days",
	"leave_balance",
}
PROBLEM_FIELDS = {"kind"}
RECENT_FIELDS = {"name", "employee_name", "actor", "action", "at"}
COUNT_FIELDS = {"pending_approvals", "on_leave_today", "opened_this_month", "problems"}
FAKE_LOGIN_TEXT = "Sahte-Parola-1165-ozet!"
COMPANY = "HRT Home Company"
ABBR = "HRTH"
LEAVE_TYPE = "HRT Home Leave"
HOLIDAY_LIST = "HRT Home Holidays"
TEAM_A = "HRT Home Team A"
TEAM_B = "HRT Home Team B"

# Role profile of each person.
PROFILES = {
	"manager": "HRT Manager",
	"worker_a": "HRT Employee",
	"worker_b": "HRT Employee",
	"peer_manager": "HRT Manager",
	"peer_worker": "HRT Employee",
	"admin": "Tenant Admin",
}
# Employee records: the manager of each one and the team (department).
EMPLOYEES = {
	"manager": (None, TEAM_A),
	"worker_a": ("manager", TEAM_A),
	"worker_b": ("manager", TEAM_A),
	"peer_manager": (None, TEAM_B),
	"peer_worker": ("peer_manager", TEAM_B),
	# A record without a user and without a joining date.
	"no_joining": ("manager", TEAM_A),
}


def day(offset: int) -> str:
	return str(add_days(today(), offset))


def row(name, team, start, end, **values):
	return {"name": name, "department": team, "from_date": start, "to_date": end, **values}


@unittest.skipIf(frappe is None, "Needs Frappe.")
class OverlapRuleTest(unittest.TestCase):
	"""Two open or approved leaves of one team that share a day are one problem."""

	def pairs(self, rows):
		return [(first["name"], second["name"]) for first, second in home_summary.find_overlaps(rows)]

	def test_shared_day_in_one_team_is_an_overlap(self):
		rows = [row("L1", "A", "2026-12-07", "2026-12-08"), row("L2", "A", "2026-12-08", "2026-12-09")]
		self.assertEqual(self.pairs(rows), [("L1", "L2")])

	def test_days_next_to_each_other_do_not_overlap(self):
		rows = [row("L1", "A", "2026-12-07", "2026-12-08"), row("L2", "A", "2026-12-09", "2026-12-10")]
		self.assertEqual(self.pairs(rows), [])

	def test_other_team_does_not_overlap(self):
		rows = [row("L1", "A", "2026-12-07", "2026-12-08"), row("L2", "B", "2026-12-07", "2026-12-08")]
		self.assertEqual(self.pairs(rows), [])

	def test_leave_without_team_is_skipped(self):
		rows = [row("L1", None, "2026-12-07", "2026-12-08"), row("L2", None, "2026-12-07", "2026-12-08")]
		self.assertEqual(self.pairs(rows), [])

	def test_long_leave_overlaps_each_later_leave_inside_it(self):
		rows = [
			row("L3", "A", "2026-12-10", "2026-12-10"),
			row("L1", "A", "2026-12-01", "2026-12-20"),
			row("L2", "A", "2026-12-05", "2026-12-05"),
		]
		self.assertEqual(self.pairs(rows), [("L1", "L2"), ("L1", "L3")])


@unittest.skipIf(frappe is None, "Needs Frappe.")
class ChangeActionRuleTest(unittest.TestCase):
	"""What the person did to the leave in its last change."""

	def action(self, **values):
		at = datetime(2026, 11, 26, 9, 40)
		return home_summary.change_action(frappe._dict({"creation": at, "modified": at, **values}))

	def test_new_open_leave_was_created(self):
		self.assertEqual(self.action(status="Open", docstatus=0), "created")

	def test_changed_open_leave_was_updated(self):
		self.assertEqual(
			self.action(status="Open", docstatus=0, modified=datetime(2026, 11, 26, 10, 0)), "updated"
		)

	def test_submitted_leave_was_approved_or_rejected(self):
		self.assertEqual(self.action(status="Approved", docstatus=1), "approved")
		self.assertEqual(self.action(status="Rejected", docstatus=1), "rejected")

	def test_cancelled_leave_was_cancelled(self):
		self.assertEqual(self.action(status="Cancelled", docstatus=2), "cancelled")
		self.assertEqual(self.action(status="Approved", docstatus=2), "cancelled")


@unittest.skipIf(frappe is None, "Needs Frappe installed.")
class BoundedSummaryQueryTest(unittest.TestCase):
	def test_employee_problem_query_has_an_explicit_positive_bound(self):
		with patch.object(home_summary, "frappe") as fake:
			fake.has_permission.return_value = True
			fake.get_list.return_value = []
			home_summary._employee_problems()
		for call in fake.get_list.call_args_list:
			self.assertGreater(call.kwargs.get("limit_page_length", call.kwargs.get("limit", 0)), 0)


@unittest.skipIf(frappe is None, "Needs a Frappe test site with HRMS TR installed.")
class HomeSummaryRequestTest(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.site = frappe.local.site
		cls.prefix = f"hrt-home-{frappe.generate_hash(length=8)}"
		cls.make_master_data()
		cls.users = {}
		for person, profile in PROFILES.items():
			email = f"{cls.prefix}-{person.replace('_', '-')}@example.test"
			frappe.get_doc(
				doctype="User",
				email=email,
				first_name=f"Synthetic {person}",
				send_welcome_email=0,
				role_profiles=[{"role_profile": profile}],
			).insert()
			update_password(email, FAKE_LOGIN_TEXT)
			cls.users[person] = email
		cls.employees = {}
		for person, (manager, team) in EMPLOYEES.items():
			cls.employees[person] = (
				frappe.get_doc(
					doctype="Employee",
					# HRMS copies this name into the user. One word each keeps the users apart.
					first_name=f"Synthetic-{person}",
					last_name=cls.prefix,
					company=COMPANY,
					department=cls.departments[team],
					status="Active",
					gender="Other",
					date_of_birth="1990-01-01",
					date_of_joining="2020-01-01",
					holiday_list=HOLIDAY_LIST,
					user_id=cls.users.get(person),
					create_user_permission=0,
					reports_to=cls.employees[manager] if manager else None,
				)
				.insert()
				.name
			)
		# Written directly: HRMS asks for a joining date, an imported record can miss it.
		frappe.db.set_value("Employee", cls.employees["no_joining"], "date_of_joining", None)
		start = getdate(today())
		month_start = get_first_day(start)
		last_month = f"{add_months(month_start, -1)} 08:00:00"
		cls.leaves = {}
		# name: owner, approver, start offset, end offset, status, docstatus, extra values.
		plan = {
			# Two open team A leaves that share a day: one problem.
			"open_a": ("worker_a", "manager", 10, 11, "Open", 0, {}),
			"open_b": ("worker_b", "manager", 11, 12, "Open", 0, {}),
			# Open but another approver: visible to the manager, not pending for the manager.
			"other_approver": ("worker_b", "admin", 20, 20, "Open", 0, {}),
			# Approved today: one person on leave today.
			"approved_today": ("worker_a", "manager", 0, 1, "Approved", 1, {}),
			# Rejected leave that shares days with open_a: a rejected leave is not a problem.
			"rejected": ("worker_b", "manager", 10, 10, "Rejected", 1, {}),
			# Opened last month.
			"last_month": ("worker_a", "manager", 30, 30, "Open", 0, {"creation": last_month}),
			# Team B shares days with open_a: another team is not a problem.
			"peer": ("peer_worker", "peer_manager", 10, 11, "Open", 0, {}),
		}
		base = now_datetime().replace(microsecond=0)
		for index, (key, (owner, approver, first, last, status, docstatus, extra)) in enumerate(plan.items()):
			# Later items changed later. The recent list orders by this value.
			modified = base + timedelta(seconds=index)
			values = {"creation": modified, **extra}
			if key in ("approved_today", "rejected"):
				# The decision is a later change by the manager.
				values["modified_by"] = cls.users["manager"]
				values["creation"] = base - timedelta(seconds=30)
			doc = frappe.get_doc(
				doctype=DOCTYPE,
				name=f"{cls.prefix}-{key}",
				naming_series="HR-LAP-.YYYY.-",
				employee=cls.employees[owner],
				employee_name=f"Synthetic {owner}",
				department=cls.departments[EMPLOYEES[owner][1]],
				company=COMPANY,
				leave_type=LEAVE_TYPE,
				leave_approver=cls.users[approver],
				from_date=day(first),
				to_date=day(last),
				total_leave_days=last - first + 1,
				leave_balance=11,
				posting_date=str(start),
				status=status,
				docstatus=docstatus,
			)
			# Written directly: allocation and holiday checks of HRMS are not the subject here.
			doc.db_insert()
			frappe.db.set_value(
				DOCTYPE,
				doc.name,
				{"modified": values.pop("modified", modified), **values},
				update_modified=False,
			)
			cls.leaves[key] = doc.name
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def make_master_data(cls):
		if not frappe.db.exists("Gender", "Other"):
			frappe.get_doc(doctype="Gender", gender="Other").insert()
		if not frappe.db.exists("Company", COMPANY):
			# Written directly: the company setup of ERPNext is not the subject of this test.
			company = frappe.get_doc(
				doctype="Company", company_name=COMPANY, abbr=ABBR, default_currency="TRY", country="Türkiye"
			)
			company.name = COMPANY
			company.db_insert()
		# A department needs a group as its parent.
		group = f"HRT Home Teams - {ABBR}"
		if not frappe.db.exists("Department", group):
			frappe.get_doc(
				doctype="Department", department_name="HRT Home Teams", company=COMPANY, is_group=1
			).insert()
		cls.departments = {}
		for team in (TEAM_A, TEAM_B):
			name = f"{team} - {ABBR}"
			if not frappe.db.exists("Department", name):
				frappe.get_doc(
					doctype="Department", department_name=team, company=COMPANY, parent_department=group
				).insert()
			cls.departments[team] = name
		if not frappe.db.exists("Holiday List", HOLIDAY_LIST):
			frappe.get_doc(
				doctype="Holiday List",
				holiday_list_name=HOLIDAY_LIST,
				from_date=add_days(today(), -400),
				to_date=add_days(today(), 400),
			).insert()
		if not frappe.db.exists(
			"Holiday List Assignment", {"assigned_to": COMPANY, "holiday_list": HOLIDAY_LIST, "docstatus": 1}
		):
			# HRMS 16 finds the holiday list of an employee through a submitted assignment.
			# Written directly: the assignment flow of HRMS is not the subject of this test.
			assignment = frappe.get_doc(
				doctype="Holiday List Assignment",
				applicable_for="Company",
				assigned_to=COMPANY,
				holiday_list=HOLIDAY_LIST,
				from_date=add_days(today(), -400),
				docstatus=1,
			)
			assignment.name = f"HR-HLA-{HOLIDAY_LIST}"
			assignment.db_insert()
		if not frappe.db.exists("Leave Type", LEAVE_TYPE):
			# Leave without pay: HRMS does not ask for an allocation.
			frappe.get_doc(doctype="Leave Type", leave_type_name=LEAVE_TYPE, is_lwp=1).insert()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for employee in cls.employees.values():
			for name in frappe.get_all(DOCTYPE, filters={"employee": employee}, pluck="name"):
				frappe.db.delete(DOCTYPE, {"name": name})
		for person in reversed(EMPLOYEES):
			frappe.delete_doc("Employee", cls.employees[person], force=True)
		for user in cls.users.values():
			frappe.delete_doc("User", user, force=True)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	# --- request helpers ---

	def send(self, client, method: str, path: str, *, body=None):
		headers = {"Accept": "application/json"}
		kwargs = {"path": path, "method": method, "headers": headers}
		if body is not None:
			headers["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def login(self, person: str):
		client = get_test_client(use_cookies=True)
		response = self.send(
			client, "POST", "/api/method/login", body={"usr": self.users[person], "pwd": FAKE_LOGIN_TEXT}
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		return client

	def state(self, key: str):
		return frappe.db.get_value(DOCTYPE, self.leaves[key], ["status", "docstatus"])

	def version(self, key: str) -> str:
		return str(frappe.db.get_value(DOCTYPE, self.leaves[key], "modified"))

	def reject(self, person: str, key: str, version: str | None = None):
		body = {"name": self.leaves[key], "version": version or self.version(key)}
		return self.send(self.login(person), "POST", REJECT, body=body)

	def summary(self, person: str) -> dict:
		response = self.send(self.login(person), "GET", SUMMARY)
		self.assertEqual(response.status_code, 200, response.data[:300])
		return response.json["message"]

	def own_names(self, names):
		return [name for name in names if name.startswith(self.prefix)]

	def saved(self, key: str) -> dict:
		fields = ("status", "docstatus", "modified", "modified_by")
		return frappe.db.get_value(DOCTYPE, self.leaves[key], fields, as_dict=True)

	def restore(self, key: str, values: dict):
		# Written directly: the other tests read the leave as it was before the rejection.
		frappe.db.set_value(DOCTYPE, self.leaves[key], values, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	# --- reject ---

	def test_approver_rejects_an_open_leave(self):
		before = self.saved("open_a")
		try:
			response = self.reject("manager", "open_a")

			self.assertEqual(response.status_code, 200, response.data[:300])
			self.assertEqual(response.json["message"], {"name": self.leaves["open_a"]})
			self.assertEqual(self.state("open_a"), ("Rejected", 1))
		finally:
			self.restore("open_a", before)

	def test_stale_version_is_refused_and_the_leave_stays(self):
		before = self.version("open_b")

		response = self.reject("manager", "open_b", version="2000-01-01 00:00:00.000001")

		self.assertEqual(response.status_code, 417, response.data[:300])
		self.assertEqual(response.json["exc_type"], "TimestampMismatchError")
		self.assertEqual(self.state("open_b"), ("Open", 0))
		self.assertEqual(self.version("open_b"), before)

	def test_user_without_the_right_cannot_reject(self):
		for person in ("peer_manager", "worker_b"):
			with self.subTest(person=person):
				response = self.reject(person, "open_a")

				self.assertEqual(response.status_code, 403, response.data[:300])
				self.assertEqual(self.state("open_a"), ("Open", 0))

	def test_reject_takes_post_only(self):
		response = self.send(self.login("manager"), "GET", REJECT)

		self.assertEqual(response.status_code, 403, response.data[:300])

	# --- summary ---

	def test_summary_takes_get_only(self):
		response = self.send(self.login("manager"), "POST", SUMMARY, body={})

		self.assertEqual(response.status_code, 403, response.data[:300])

	def test_summary_has_the_contract_parts(self):
		data = self.summary("admin")

		self.assertEqual(set(data), SUMMARY_PARTS)
		for part, fields in (
			("pending_approvals", PENDING_FIELDS),
			("problems", PROBLEM_FIELDS),
			("recent_changes", RECENT_FIELDS),
		):
			self.assertTrue(data[part], part)
			for item in data[part]:
				with self.subTest(part=part, item=item):
					self.assertLessEqual(fields, set(item))
		self.assertEqual(set(data["counts"]), COUNT_FIELDS)

	def test_pending_lists_only_open_leaves_of_the_signed_in_approver(self):
		pending = self.summary("manager")["pending_approvals"]

		# Ordered by the first leave day. "other_approver" waits for another approver.
		self.assertEqual(
			self.own_names(item["name"] for item in pending),
			[self.leaves[key] for key in ("open_a", "open_b", "last_month")],
		)
		first = pending[0]
		self.assertEqual(first["version"], self.version("open_a"))
		self.assertEqual(first["employee_name"], "Synthetic worker_a")
		self.assertEqual(first["leave_type"], LEAVE_TYPE)
		self.assertEqual((first["from_date"], first["to_date"]), (day(10), day(11)))
		self.assertEqual(first["total_leave_days"], 2)
		self.assertEqual(first["leave_balance"], 11)

	def test_pending_is_empty_without_waiting_leaves(self):
		data = self.summary("worker_a")

		self.assertEqual(data["pending_approvals"], [])
		self.assertEqual(data["counts"]["pending_approvals"], 0)

	def test_overlap_of_one_team_is_a_problem(self):
		problems = self.summary("manager")["problems"]

		overlaps = [
			sorted(leave["name"] for leave in item["leaves"])
			for item in problems
			if item["kind"] == "overlap" and item["leaves"][0]["name"].startswith(self.prefix)
		]
		self.assertEqual(overlaps, [sorted([self.leaves["open_a"], self.leaves["open_b"]])])

	def test_missing_joining_date_is_a_problem_for_a_reader_of_employees(self):
		problems = self.summary("admin")["problems"]

		missing = [item["employee"] for item in problems if item["kind"] == "missing_joining_date"]
		self.assertIn(self.employees["no_joining"], missing)
		self.assertNotIn(self.employees["worker_a"], missing)

	def test_employee_problems_stay_hidden_without_employee_read(self):
		problems = self.summary("manager")["problems"]

		self.assertEqual([item for item in problems if item["kind"] == "missing_joining_date"], [])

	def test_recent_changes_are_the_last_five_visible_changes(self):
		recent = self.summary("manager")["recent_changes"]

		# The manager sees team A only. The peer leave is newest but hidden.
		expected = ["last_month", "rejected", "approved_today", "other_approver", "open_b"]
		self.assertEqual([item["name"] for item in recent], [self.leaves[key] for key in expected])
		actions = {item["name"]: item["action"] for item in recent}
		self.assertEqual(actions[self.leaves["rejected"]], "rejected")
		self.assertEqual(actions[self.leaves["approved_today"]], "approved")
		self.assertEqual(actions[self.leaves["open_b"]], "created")
		by_name = {item["name"]: item for item in recent}

		# The actor is the user who made the change, not the employee of the leave.
		# HRMS copies the employee name into the user, so the name is read from the user.
		# The name of this process is cached, so the test reads it from the table.
		def full_name(person):
			names = frappe.db.get_value("User", self.users[person], ["first_name", "last_name"])
			return " ".join(filter(None, names))

		actor = by_name[self.leaves["rejected"]]["actor"]
		self.assertEqual(actor, full_name("manager"))
		self.assertNotEqual(actor, full_name("worker_b"))
		self.assertEqual(by_name[self.leaves["rejected"]]["at"], self.version("rejected"))

	def test_counts_follow_the_visible_records(self):
		counts = self.summary("manager")["counts"]

		self.assertEqual(
			counts,
			{
				"pending_approvals": 3,
				"on_leave_today": 1,
				"opened_this_month": 5,
				"problems": 1,
			},
		)

	def test_summary_limits_queries_without_truncating_visible_counts(self):
		# More than one displayed page, all visible to the manager.
		added = home_summary.LIST_LIMIT + 5
		names = []
		try:
			for index in range(added):
				doc = frappe.copy_doc(frappe.get_doc(DOCTYPE, self.leaves["open_a"]))
				doc.name = f"{self.prefix}-bulk-{index:03d}"
				doc.from_date = day(40)
				doc.to_date = day(40)
				doc.db_insert()
				names.append(doc.name)
			frappe.set_user(self.users["manager"])
			with patch.object(frappe, "get_list", wraps=frappe.get_list) as listed:
				data = home_summary.get_summary()
			self.assertEqual(data["counts"]["pending_approvals"], added + 3)
			self.assertEqual(data["counts"]["opened_this_month"], added + 5)
			self.assertEqual(data["counts"]["problems"], added * (added - 1) // 2 + 1)
			self.assertEqual(len(data["pending_approvals"]), home_summary.LIST_LIMIT)
			self.assertEqual(len(data["problems"]), home_summary.LIST_LIMIT)
			for call in listed.call_args_list:
				if call.args[0] not in (DOCTYPE, "Employee"):
					continue
				limit = call.kwargs.get("limit_page_length", call.kwargs.get("limit"))
				self.assertIsNotNone(limit, call)
				self.assertGreater(limit, 0, call)
				self.assertLessEqual(limit, home_summary.LIST_LIMIT, call)
		finally:
			frappe.set_user("Administrator")
			frappe.db.delete(DOCTYPE, {"name": ["in", names]})

	def test_distinct_employees_and_missing_dates_count_beyond_the_list_limit(self):
		added = home_summary.LIST_LIMIT + 5
		employees, leaves = [], []
		try:
			for index in range(added):
				employee = frappe.copy_doc(frappe.get_doc("Employee", self.employees["worker_a"]))
				employee.name = f"{self.prefix}-bulk-employee-{index:03d}"
				employee.user_id = None
				employee.date_of_joining = None
				employee.db_insert()
				employees.append(employee.name)
				for suffix in ("a", "b"):
					doc = frappe.copy_doc(frappe.get_doc(DOCTYPE, self.leaves["approved_today"]))
					doc.name = f"{self.prefix}-bulk-approved-{index:03d}-{suffix}"
					doc.employee = employee.name
					doc.department = None
					doc.db_insert()
					leaves.append(doc.name)
			frappe.set_user(self.users["admin"])
			with patch.object(frappe, "get_list", wraps=frappe.get_list) as listed:
				data = home_summary.get_summary()
			self.assertEqual(data["counts"]["on_leave_today"], added + 1)
			self.assertEqual(data["counts"]["problems"], added + 2)
			self.assertEqual(len(data["problems"]), home_summary.LIST_LIMIT)
			for call in listed.call_args_list:
				if call.args[0] not in (DOCTYPE, "Employee"):
					continue
				self.assertGreater(call.kwargs.get("limit_page_length", call.kwargs.get("limit", 0)), 0)
		finally:
			frappe.set_user("Administrator")
			frappe.db.delete(DOCTYPE, {"name": ["in", leaves]})
			frappe.db.delete("Employee", {"name": ["in", employees]})

	def test_overlap_query_counts_nested_and_boundary_ranges_once(self):
		names = []
		try:
			for suffix, first, last, team in (
				("z-long", 50, 60, TEAM_A),
				("a-inner", 52, 53, TEAM_A),
				("b-boundary", 60, 61, TEAM_A),
				("c-next", 62, 63, TEAM_A),
				("d-other", 52, 53, TEAM_B),
				("e-no-team", 52, 53, None),
			):
				doc = frappe.copy_doc(frappe.get_doc(DOCTYPE, self.leaves["open_a"]))
				doc.name = f"{self.prefix}-range-{suffix}"
				doc.from_date, doc.to_date = day(first), day(last)
				doc.department = self.departments[team] if team else None
				doc.db_insert()
				names.append(doc.name)
			frappe.set_user(self.users["manager"])
			data = home_summary.get_summary()
			self.assertEqual(data["counts"]["problems"], 3)
			pairs = {frozenset(leave["name"] for leave in item["leaves"]) for item in data["problems"]}
			self.assertEqual(
				pairs,
				{
					frozenset((self.leaves["open_a"], self.leaves["open_b"])),
					frozenset((names[0], names[1])),
					frozenset((names[0], names[2])),
				},
			)
		finally:
			frappe.set_user("Administrator")
			frappe.db.delete(DOCTYPE, {"name": ["in", names]})


if __name__ == "__main__":
	unittest.main()
