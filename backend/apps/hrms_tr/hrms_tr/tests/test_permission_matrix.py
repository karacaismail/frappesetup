"""Permission matrix of HRMS TR leave applications (G-104).

The matrix below is the permission table of the app. It states, for each role profile, which
leave applications a person sees, what the person may do with them and which field levels
the person reads and writes. Two checks hold it in place:

- `MatrixFixtureTest` compares the table with the shipped fixtures (roles, role profiles,
  access rules, custom permissions and the leave balance field level).
- `PermissionMatrixIntegrationTest` signs in as each person on a test site and compares what
  Frappe returns with the same table. It uses the real permission hooks of Frappe, the access
  engine of platform_core and the installed HRMS TR fixtures.

Example tree (all people and records are made up):

    manager ── employee ── indirect
    peer_manager ── peer_employee
"""

import json
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DOCTYPE = "Leave Application"
BALANCE_FIELD = "leave_balance"
STATUS_FIELD = "status"

# Role profile of each person. `None` means a website user without an HRMS TR role.
PROFILES = {
	"manager": "HRT Manager",
	"employee": "HRT Employee",
	"indirect": "HRT Employee",
	"peer_manager": "HRT Manager",
	"peer_employee": "HRT Employee",
	"admin": "HRT Admin",
	"outsider": None,
}
# The person each employee reports to. People missing here have no employee record.
REPORTS_TO = {
	"manager": None,
	"employee": "manager",
	"indirect": "employee",
	"peer_manager": None,
	"peer_employee": "peer_manager",
}
RECORD_OWNERS = tuple(REPORTS_TO)

# Whose leave applications each person sees in a list.
VISIBLE = {
	"manager": {"manager", "employee", "indirect"},
	"employee": {"employee"},
	"indirect": {"indirect"},
	"peer_manager": {"peer_manager", "peer_employee"},
	"peer_employee": {"peer_employee"},
	"admin": set(RECORD_OWNERS),
	"outsider": set(),
}

# What a person may do with one draft leave application, by the relation to its owner.
# own: the person's own application; report: someone in the person's reporting tree;
# other: someone outside it.
ACTIONS = {
	"HRT Employee": {
		"own": {"read": True, "write": True, "submit": False, "cancel": False},
		"other": {"read": False, "write": False, "submit": False, "cancel": False},
	},
	"HRT Manager": {
		"own": {"read": True, "write": True},
		"report": {"read": True, "write": True, "submit": True, "cancel": False},
		"other": {"read": False, "write": False, "submit": False, "cancel": False},
	},
	"HRT Admin": {
		"other": {"read": True, "write": True, "submit": True, "cancel": True},
	},
	None: {
		"other": {"read": False, "write": False, "submit": False, "cancel": False},
	},
}
CREATE = {"HRT Employee": True, "HRT Manager": True, "HRT Admin": True, None: False}

# Field levels each profile reads and writes on a leave application.
# Level 1 holds `status`: everyone reads it, only approvers write it, so only they approve.
# Level 2 holds the leave balance.
LEVELS = {
	"HRT Employee": {"read": {0, 1}, "write": {0}},
	"HRT Manager": {"read": {0, 1, 2}, "write": {0, 1}},
	"HRT Admin": {"read": {0, 1, 2}, "write": {0, 1}},
}

# Frappe copies the standard rows of HRMS into "Custom DocPerm" when the first custom row is
# added. This standard row is the one the HRMS TR roles share: every user reads level 1.
INHERITED_ROWS = ({"role": "All", "permlevel": 1, "read": 1, "write": 0},)

RULE_SCOPE = {"HRT Employee": "own", "HRT Manager": "team", "HRT Admin": "all"}
RULE_FLAGS = ("read", "create", "write", "submit", "cancel")


def fixture(name):
	return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def profiles():
	# The Role Profiles are not fixtures (AJA-934). `hrms_tr.role_profiles` opens them from this file.
	return json.loads((FIXTURES.parent / "role_profile.json").read_text(encoding="utf-8"))


def profile_roles(profile):
	for row in profiles():
		if row["name"] == profile:
			return {role["role"] for role in row["roles"]}
	raise AssertionError(f"Missing role profile {profile}")


def relation(person, owner):
	if person == owner:
		return "own"
	manager = REPORTS_TO.get(owner)
	while manager:
		if manager == person:
			return "report"
		manager = REPORTS_TO.get(manager)
	return "other"


def expected_actions(person, owner):
	table = ACTIONS[PROFILES[person]]
	return table.get(relation(person, owner), table["other"])


class MatrixFixtureTest(unittest.TestCase):
	"""The permission table must say the same thing as the shipped fixtures."""

	def test_every_profile_has_a_role_and_a_profile_fixture(self):
		roles = {row["name"] for row in fixture("01_role.json")}
		for profile in RULE_SCOPE:
			with self.subTest(profile=profile):
				self.assertIn(profile, roles)
				self.assertIn(profile, profile_roles(profile))

	def test_rule_scopes_follow_the_reporting_relation(self):
		rules = {
			row["role"]: row for row in fixture("03_access_rule.json") if row["document_type"] == DOCTYPE
		}
		for role, scope in RULE_SCOPE.items():
			with self.subTest(role=role):
				self.assertEqual(rules[role]["scope"], scope)
				self.assertEqual(rules[role]["is_active"], 1)
				if scope != "all":
					# The engine compares this field with the person's employee tree.
					self.assertEqual(rules[role]["match_field"], "employee")

	def test_rule_flags_match_the_widest_action_of_each_role(self):
		rules = {
			row["role"]: row for row in fixture("03_access_rule.json") if row["document_type"] == DOCTYPE
		}
		widest = {"HRT Employee": "own", "HRT Manager": "report", "HRT Admin": "other"}
		for role, cell in widest.items():
			actions = ACTIONS[role][cell]
			for flag in ("read", "write", "submit", "cancel"):
				with self.subTest(role=role, flag=flag):
					self.assertEqual(bool(rules[role][f"allow_{flag}"]), actions[flag])

	def test_custom_permissions_give_the_level_table(self):
		rows = [row for row in fixture("05_custom_docperm.json") if row["parent"] == DOCTYPE]
		rows += list(INHERITED_ROWS)
		for profile, levels in LEVELS.items():
			roles = profile_roles(profile) | {"All"}
			for ptype, expected in levels.items():
				with self.subTest(profile=profile, ptype=ptype):
					granted = {row["permlevel"] for row in rows if row["role"] in roles and row.get(ptype)}
					self.assertEqual(granted, expected)

	def test_create_and_cancel_rows_match_the_table(self):
		rows = [row for row in fixture("05_custom_docperm.json") if row["parent"] == DOCTYPE]
		for profile in LEVELS:
			roles = profile_roles(profile)
			with self.subTest(profile=profile):
				level_0 = [row for row in rows if row["role"] in roles and row["permlevel"] == 0]
				self.assertEqual(any(row["create"] for row in level_0), CREATE[profile])
				self.assertEqual(any(row["cancel"] for row in level_0), ACTIONS[profile]["other"]["cancel"])

	def test_leave_balance_is_on_level_2(self):
		setter = {row["name"]: row for row in fixture("04_property_setter.json")}
		row = setter[f"{DOCTYPE}-{BALANCE_FIELD}-permlevel"]
		self.assertEqual(
			(row["field_name"], row["property"], row["value"]), (BALANCE_FIELD, "permlevel", "2")
		)

	def test_relation_helper_follows_the_tree(self):
		self.assertEqual(relation("manager", "indirect"), "report")
		self.assertEqual(relation("employee", "indirect"), "report")
		self.assertEqual(relation("indirect", "employee"), "other")
		self.assertEqual(relation("peer_manager", "employee"), "other")


try:
	import frappe
	from frappe.tests import IntegrationTestCase
except ImportError:  # Outside a bench the static checks above still run.
	frappe = None
	IntegrationTestCase = unittest.TestCase


@unittest.skipIf(frappe is None, "Needs a Frappe test site with HRMS TR installed.")
class PermissionMatrixIntegrationTest(IntegrationTestCase):
	"""Each person signs in and Frappe's answers are compared with the table."""

	COMPANY = "HRT Matrix Company"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.prefix = f"hrt-matrix-{frappe.generate_hash(length=8)}"
		if not frappe.db.exists("Gender", "Other"):
			frappe.get_doc(doctype="Gender", gender="Other").insert()
		if not frappe.db.exists("Company", cls.COMPANY):
			# Written directly: the company setup of ERPNext is not the subject of this test.
			company = frappe.get_doc(
				doctype="Company",
				company_name=cls.COMPANY,
				abbr="HRTM",
				default_currency="TRY",
				country="Türkiye",
			)
			company.name = cls.COMPANY
			company.db_insert()
		cls.users = {}
		for person, profile in PROFILES.items():
			email = f"{cls.prefix}-{person.replace('_', '-')}@example.test"
			frappe.get_doc(
				doctype="User",
				email=email,
				first_name=f"Synthetic {person}",
				send_welcome_email=0,
				user_type="Website User",
				role_profiles=[{"role_profile": profile}] if profile else [],
			).insert()
			cls.users[person] = email
		cls.employees = {}
		for person in RECORD_OWNERS:
			manager = REPORTS_TO[person]
			cls.employees[person] = (
				frappe.get_doc(
					doctype="Employee",
					first_name=f"Synthetic {person}",
					company=cls.COMPANY,
					status="Active",
					gender="Other",
					date_of_birth="1990-01-01",
					date_of_joining="2020-01-01",
					user_id=cls.users[person],
					create_user_permission=0,
					reports_to=cls.employees[manager] if manager else None,
				)
				.insert()
				.name
			)
		cls.leaves = {}
		for person in RECORD_OWNERS:
			# Written directly: leave allocation and holiday checks of HRMS are not the subject here.
			doc = frappe.get_doc(
				doctype=DOCTYPE,
				name=f"{cls.prefix}-{person}",
				employee=cls.employees[person],
				company=cls.COMPANY,
				from_date="2026-12-01",
				to_date="2026-12-01",
				status="Open",
				leave_balance=7,
				docstatus=0,
			)
			doc.db_insert()
			cls.leaves[person] = doc.name
		cls.owner_of = {name: person for person, name in cls.leaves.items()}

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def sign_in(self, person):
		"""Acts as a new request of the person: values kept for one request are dropped."""
		frappe.set_user(self.users[person])
		frappe.local.hrms_tr_access_rules_active = None
		cache = getattr(frappe.local, "request_cache", None)
		if cache is not None:
			cache.clear()

	def test_inherited_level_1_row_is_on_the_site(self):
		for row in INHERITED_ROWS:
			with self.subTest(role=row["role"]):
				stored = frappe.get_all(
					"Custom DocPerm",
					filters={"parent": DOCTYPE, "role": row["role"], "permlevel": row["permlevel"]},
					fields=["read", "write"],
				)
				self.assertEqual([(r.read, r.write) for r in stored], [(row["read"], row["write"])])

	def test_people_hold_only_hrms_tr_roles(self):
		hrms_tr_roles = {"HRT Employee", "HRT Manager", "HRT Admin", "All", "Guest"}
		for person in PROFILES:
			with self.subTest(person=person):
				roles = set(frappe.get_roles(self.users[person]))
				# Native HRMS roles would add their own standard rows to the table.
				self.assertLessEqual(roles, hrms_tr_roles)

	def test_users_are_website_users_with_their_profile(self):
		for person, profile in PROFILES.items():
			with self.subTest(person=person):
				user = frappe.get_doc("User", self.users[person])
				self.assertEqual(user.user_type, "Website User")
				roles = {row.role for row in user.roles}
				expected = profile_roles(profile) if profile else set()
				self.assertEqual(roles & {"HRT Employee", "HRT Manager", "HRT Admin"}, expected)

	def test_list_shows_the_records_in_the_table(self):
		for person, expected in VISIBLE.items():
			with self.subTest(person=person):
				self.sign_in(person)
				try:
					names = frappe.get_list(
						DOCTYPE,
						filters={"name": ["like", f"{self.prefix}-%"]},
						pluck="name",
						limit_page_length=0,
					)
				except frappe.PermissionError:
					names = []
				self.assertEqual({self.owner_of[name] for name in names}, expected)

	def test_document_actions_match_the_table(self):
		for person in PROFILES:
			for owner, name in self.leaves.items():
				expected = expected_actions(person, owner)
				for ptype, allowed in expected.items():
					with self.subTest(person=person, owner=owner, ptype=ptype):
						self.sign_in(person)
						result = frappe.has_permission(DOCTYPE, ptype, doc=name, user=self.users[person])
						self.assertEqual(bool(result), allowed)

	def test_create_matches_the_table(self):
		for person, profile in PROFILES.items():
			with self.subTest(person=person):
				self.sign_in(person)
				self.assertEqual(
					bool(frappe.has_permission(DOCTYPE, "create", user=self.users[person])), CREATE[profile]
				)

	def test_sensitive_fields_follow_the_level_table(self):
		from frappe.client import get as client_get

		for person in ("employee", "manager", "admin"):
			levels = LEVELS[PROFILES[person]]
			with self.subTest(person=person):
				self.sign_in(person)
				data = client_get(DOCTYPE, self.leaves["employee"])
				self.assertEqual(BALANCE_FIELD in data, 2 in levels["read"])
				self.assertEqual(STATUS_FIELD in data, 1 in levels["read"])
				doc = frappe.get_doc(DOCTYPE, self.leaves["employee"])
				self.assertEqual(set(doc.get_permlevel_access("write")), levels["write"])

	def test_reporting_change_moves_the_record_to_the_new_manager(self):
		frappe.db.savepoint("before_reports_to_change")
		try:
			employee = frappe.get_doc("Employee", self.employees["indirect"])
			employee.reports_to = self.employees["peer_manager"]
			employee.save()
			for person, sees in (("manager", False), ("employee", False), ("peer_manager", True)):
				with self.subTest(person=person):
					self.sign_in(person)
					self.assertEqual(
						bool(frappe.has_permission(DOCTYPE, "read", doc=self.leaves["indirect"])), sees
					)
		finally:
			frappe.set_user("Administrator")
			frappe.db.rollback(save_point="before_reports_to_change")
