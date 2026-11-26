"""Leave applications of the two tenant panel roles (AJA-947, G-62, G-168). Written before the code.

The panel page “İzin talepleri” reads “Leave Application”. The product owner decided:

| Role                     | Reads every leave of the site | Opens | Approves | Rejects | Deletes |
| ------------------------ | ----------------------------- | ----- | -------- | ------- | ------- |
| "Tenant Admin"           | Yes                           | Yes   | Yes      | Yes     | No      |
| "Tenant Admin Assistant" | Yes                           | Yes   | No       | No      | No      |

A tenant is its own Frappe site. A leave of another tenant is not on this site, so its name
cannot be read here.

Both roles choose an employee when they open a leave. They never read the personal fields
of the employee record (AJA-1024).

The requests go through the WSGI application of Frappe with a real session. The test needs a
Frappe test site with HRMS TR and platform_core installed:
`PANE_PORT=<port> backend/dev/bin/test hrms_tr --module hrms_tr.tests.test_panel_roles`.
All people, companies and records are made up.
"""

import json
import unittest

try:
	import frappe
	from frappe.tests import IntegrationTestCase
	from frappe.tests.test_api import make_request
	from frappe.utils import get_test_client
	from frappe.utils.password import update_password

	from hrms_tr import leave, setup
except ImportError:  # Outside a bench the test is skipped.
	frappe = None
	IntegrationTestCase = unittest.TestCase

DOCTYPE = "Leave Application"
TENANT_ADMIN = "Tenant Admin"
TENANT_ADMIN_ASSISTANT = "Tenant Admin Assistant"
META = "/api/method/platform_core.api.meta.get_doctype"
APPROVE = "/api/method/hrms_tr.api.approve_leave"
REST = "/api/v2/document/"
FAKE_LOGIN_TEXT = "Sahte-Parola-947-izin!"
COMPANY = "HRT Panel Role Company"
LEAVE_TYPE = "HRT Panel Role Leave"
HOLIDAY_LIST = "HRT Panel Role Holidays"
# The name of a leave that lives on another tenant's site.
FOREIGN_LEAVE = "baska-kiraci-izin-947"
SEARCH_LINK = "/api/method/frappe.desk.search.search_link"
# Made-up personal values of the employee. No response to the two roles may carry them.
DATE_OF_BIRTH = "1990-01-01"
PERSONAL_VALUES = {
	"iban": "TR330006100519786457841947",
	"bank_ac_no": "9470001024",
	"passport_number": "U94710240",
	"health_details": "Sahte saglik notu 1024",
}


@unittest.skipIf(frappe is None, "Needs a Frappe test site with HRMS TR installed.")
class PanelRoleLeaveCase(IntegrationTestCase):
	"""Shared setup. A subclass sets `ROLE`."""

	ROLE = ""
	new_leaves = 0

	@classmethod
	def setUpClass(cls):
		if not cls.ROLE:
			raise unittest.SkipTest("The shared base has no role.")
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.site = frappe.local.site
		cls.prefix = f"hrt-panel-{frappe.generate_hash(length=8)}"
		cls.user = f"{cls.prefix}-{cls.ROLE.lower().replace(' ', '-')}@example.test"
		if not frappe.db.exists("Role Profile", cls.ROLE):
			raise AssertionError(f"The {cls.ROLE!r} Role Profile does not exist on the site")
		cls.make_master_data()
		frappe.get_doc(
			doctype="User",
			email=cls.user,
			first_name=f"Synthetic {cls.ROLE}",
			send_welcome_email=0,
			role_profiles=[{"role_profile": cls.ROLE}],
		).insert()
		update_password(cls.user, FAKE_LOGIN_TEXT)
		cls.employee = (
			frappe.get_doc(
				doctype="Employee",
				first_name=f"Synthetic worker {cls.prefix}",
				company=COMPANY,
				status="Active",
				gender="Other",
				date_of_birth="1990-01-01",
				date_of_joining="2020-01-01",
				holiday_list=HOLIDAY_LIST,
				create_user_permission=0,
			)
			.insert()
			.name
		)
		# Written directly: the personal values are test data, not the subject of a form.
		frappe.db.set_value("Employee", cls.employee, PERSONAL_VALUES, update_modified=False)
		cls.leaves = [cls.insert_leave(index) for index in range(2)]
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def make_master_data(cls):
		if not frappe.db.exists("Gender", "Other"):
			frappe.get_doc(doctype="Gender", gender="Other").insert()
		if not frappe.db.exists("Company", COMPANY):
			# Written directly: the company setup of ERPNext is not the subject of this test.
			company = frappe.get_doc(
				doctype="Company",
				company_name=COMPANY,
				abbr="HRTP",
				default_currency="TRY",
				country="Türkiye",
			)
			company.name = COMPANY
			company.db_insert()
		if not frappe.db.exists("Holiday List", HOLIDAY_LIST):
			frappe.get_doc(
				doctype="Holiday List",
				holiday_list_name=HOLIDAY_LIST,
				from_date="2026-01-01",
				to_date="2027-12-31",
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
				from_date="2026-01-01",
				docstatus=1,
			)
			assignment.name = f"HR-HLA-{HOLIDAY_LIST}"
			assignment.db_insert()
		if not frappe.db.exists("Leave Type", LEAVE_TYPE):
			# Leave without pay: HRMS does not ask for an allocation.
			frappe.get_doc(doctype="Leave Type", leave_type_name=LEAVE_TYPE, is_lwp=1).insert()

	@classmethod
	def insert_leave(cls, index: int) -> str:
		# Written directly: leave allocation and holiday checks of HRMS are not the subject here.
		doc = frappe.get_doc(
			doctype=DOCTYPE,
			name=f"{cls.prefix}-{index}",
			# db_insert skips the naming step. The submit still asks for the series.
			naming_series="HR-LAP-.YYYY.-",
			employee=cls.employee,
			company=COMPANY,
			leave_type=LEAVE_TYPE,
			# One day per leave: HRMS rejects two leaves of one employee on the same day.
			from_date=f"2026-12-0{7 + index}",
			to_date=f"2026-12-0{7 + index}",
			posting_date="2026-11-26",
			status="Open",
			docstatus=0,
		)
		doc.db_insert()
		return doc.name

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in frappe.get_all(DOCTYPE, filters={"employee": cls.employee}, pluck="name"):
			frappe.db.delete(DOCTYPE, {"name": name})
		frappe.delete_doc("Employee", cls.employee, force=True)
		frappe.delete_doc("User", cls.user, force=True)
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

	def send(self, client, method: str, path: str, *, body=None, query=None):
		headers = {"Accept": "application/json"}
		kwargs = {"path": path, "method": method, "headers": headers}
		if body is not None:
			headers["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		if query:
			kwargs["query_string"] = query
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def login(self):
		client = get_test_client(use_cookies=True)
		response = self.send(
			client, "POST", "/api/method/login", body={"usr": self.user, "pwd": FAKE_LOGIN_TEXT}
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		return client

	def leave_state(self, name: str):
		return frappe.db.get_value(DOCTYPE, name, ["status", "docstatus"])

	def version(self, name: str) -> str:
		return str(frappe.db.get_value(DOCTYPE, name, "modified"))

	def approve(self, client, name: str):
		return self.send(client, "POST", APPROVE, body={"name": name, "version": self.version(name)})

	def reject(self, client, name: str):
		"""Rejecting is a submit with the status “Rejected”."""
		return self.send(
			client, "PUT", REST + f"{DOCTYPE}/{name}", body={"status": "Rejected", "docstatus": 1}
		)

	def new_leave_body(self) -> dict:
		# A new day for each new leave: HRMS rejects two leaves of one employee on the same day.
		type(self).new_leaves += 1
		day = f"2026-12-{13 + type(self).new_leaves}"
		return {
			"employee": self.employee,
			"company": COMPANY,
			"leave_type": LEAVE_TYPE,
			"from_date": day,
			"to_date": day,
			"posting_date": "2026-11-26",
		}

	# --- tests of both roles ---

	def test_holder_reads_the_leave_schema(self):
		response = self.send(self.login(), "GET", META, query={"doctype": DOCTYPE})

		self.assertEqual(response.status_code, 200, response.data[:300])

	def test_holder_reads_every_leave_of_the_site(self):
		query = {
			"filters": json.dumps([["name", "like", f"{self.prefix}-%"]]),
			"fields": json.dumps(["name"]),
		}
		response = self.send(self.login(), "GET", REST + DOCTYPE, query=query)

		self.assertEqual(response.status_code, 200, response.data[:300])
		names = {row["name"] for row in response.json["data"]}
		self.assertEqual(names, set(self.leaves))

	def test_holder_opens_a_leave(self):
		response = self.send(self.login(), "POST", REST + DOCTYPE, body=self.new_leave_body())

		self.assertEqual(response.status_code, 200, response.data[:300])
		name = response.json["data"]["name"]
		self.assertEqual(self.leave_state(name), ("Open", 0))

	def test_holder_cannot_delete_a_leave(self):
		response = self.send(self.login(), "DELETE", REST + f"{DOCTYPE}/{self.leaves[0]}")

		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertTrue(frappe.db.exists(DOCTYPE, self.leaves[0]))

	def test_holder_cannot_read_a_leave_of_another_tenant(self):
		"""One test site holds one tenant. The same request reads a real leave of this site first.

		Without that first read the test would pass for a role that reads no leave at all.
		"""
		client = self.login()
		own = self.send(client, "GET", REST + f"{DOCTYPE}/{self.leaves[0]}")
		self.assertEqual(own.status_code, 200, own.data[:300])
		self.assertEqual(own.json["data"]["employee"], self.employee)
		self.assertFalse(frappe.db.exists(DOCTYPE, FOREIGN_LEAVE))

		response = self.send(client, "GET", REST + f"{DOCTYPE}/{FOREIGN_LEAVE}")

		self.assertIn(response.status_code, (403, 404), response.data[:300])
		self.assertNotIn(b'"employee"', response.data)

	def test_holder_selects_the_employee_of_a_leave(self):
		body = {"doctype": "Employee", "txt": self.prefix, "reference_doctype": DOCTYPE}
		response = self.send(self.login(), "POST", SEARCH_LINK, body=body)

		self.assertEqual(response.status_code, 200, response.data[:300])
		values = {row["value"] for row in response.json["message"]}
		self.assertIn(self.employee, values)

	def test_personal_employee_fields_are_above_level_0_on_the_site(self):
		meta = frappe.get_meta("Employee")
		for field in setup.EMPLOYEE_PERSONAL_FIELDS:
			with self.subTest(field=field):
				self.assertIsNotNone(meta.get_field(field), field)
				self.assertEqual(meta.get_field(field).permlevel, setup.EMPLOYEE_PERSONAL_LEVEL)

	def test_holder_does_not_read_the_personal_fields_of_an_employee(self):
		client = self.login()
		fields = json.dumps(["name", "date_of_birth", *PERSONAL_VALUES])
		requests = {
			"record": ("GET", REST + f"Employee/{self.employee}", None),
			"list": (
				"GET",
				REST + "Employee",
				{"fields": fields, "filters": json.dumps({"name": self.employee})},
			),
			"value": (
				"GET",
				"/api/method/frappe.client.get_value",
				{"doctype": "Employee", "filters": self.employee, "fieldname": fields},
			),
		}
		for label, (method, path, query) in requests.items():
			with self.subTest(request=label):
				response = self.send(client, method, path, query=query)
				for value in (DATE_OF_BIRTH, *PERSONAL_VALUES.values()):
					self.assertNotIn(value.encode(), response.data, (label, response.status_code))


class TenantAdminLeaveTest(PanelRoleLeaveCase):
	ROLE = TENANT_ADMIN

	def test_admin_approves_a_leave(self):
		response = self.approve(self.login(), self.leaves[0])

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(self.leave_state(self.leaves[0]), ("Approved", 1))

	def test_admin_rejects_a_leave(self):
		response = self.reject(self.login(), self.leaves[1])

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(self.leave_state(self.leaves[1]), ("Rejected", 1))


class TenantAdminAssistantLeaveTest(PanelRoleLeaveCase):
	ROLE = TENANT_ADMIN_ASSISTANT

	def test_assistant_cannot_approve_a_leave(self):
		response = self.approve(self.login(), self.leaves[0])

		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(self.leave_state(self.leaves[0]), ("Open", 0))

	def test_assistant_cannot_reject_a_leave(self):
		response = self.reject(self.login(), self.leaves[1])

		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertEqual(self.leave_state(self.leaves[1]), ("Open", 0))

	def test_assistant_cannot_reject_through_the_approval_policy(self):
		"""The policy refuses a rejection by a role that does not approve, not only the submit right."""
		frappe.set_user(self.user)
		doc = frappe.get_doc(DOCTYPE, self.leaves[1])
		# The policy compares the record with its stored version, as a save does.
		doc.load_doc_before_save()
		doc.status = "Rejected"

		with self.assertRaises(frappe.PermissionError):
			leave.validate_approval(doc)

	def test_assistant_cannot_set_the_status_when_opening_a_leave(self):
		body = {**self.new_leave_body(), "status": "Approved", "docstatus": 1}
		response = self.send(self.login(), "POST", REST + DOCTYPE, body=body)

		if response.status_code == 200:
			self.assertEqual(self.leave_state(response.json["data"]["name"]), ("Open", 0))
		else:
			self.assertEqual(response.status_code, 403, response.data[:300])
