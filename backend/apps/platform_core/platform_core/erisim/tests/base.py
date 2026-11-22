"""Shared base of the access rule tests.

The tests send the request through the WSGI application of Frappe (D-6). So the session, the HTTP method
and the permission hooks run on the real path. The expected results come from the decision note
(`docs/kararlar/0006-erisim-kurali.md`), from the contract
(`contracts/platform_core-erisim.openapi.yaml`) and from items G-60, G-61 and G-121
of the decision site (D-1). All people and records are made up.

Example tree:

    yonetici1 ── calisan1 ── calisan4
              └─ calisan2
    yonetici2 ── calisan3
"""

import json
import subprocess

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_bench_path, get_test_client
from frappe.utils.background_jobs import get_queues
from frappe.utils.password import update_password

API = "/api/method/platform_core.api.access."
REST = "/api/v2/document/"
DOCTYPE = "ER Test Talep"
FREE_DOCTYPE = "ER Test Serbest"
RULE_DOCTYPE = "Access Rule"
COMPANY = "ER Test Sirket"
GENDER = "Other"
PASSWORD = "Sahte-Parola-6150-er!"

ROLE_EMPLOYEE = "ER Calisan"
ROLE_MANAGER = "ER Yonetici"
ROLE_HR = "ER IK"
ROLE_NO_RULE = "ER Kuralsiz"
# A role without desk access. Its only member is a Website User, as the panel's users are.
ROLE_PORTAL = "ER Portal"
# A desk role that has no permission on the test types: a desk user with nothing to do there.
ROLE_DESK_ONLY = "ER Masa"

EMPLOYEE_1 = "er.calisan1@example.test"
EMPLOYEE_2 = "er.calisan2@example.test"
EMPLOYEE_3 = "er.calisan3@example.test"
EMPLOYEE_4 = "er.calisan4@example.test"
MANAGER_1 = "er.yonetici1@example.test"
MANAGER_2 = "er.yonetici2@example.test"
HR = "er.ik@example.test"
NO_RULE = "er.kuralsiz@example.test"
ADMIN = "er.admin@example.test"
PORTAL = "er.portal@example.test"
DESK_ONLY = "er.masa@example.test"

# The user, the roles and the manager the user reports to. `None` shows that there is no employee record.
PEOPLE = (
	(MANAGER_1, [ROLE_EMPLOYEE, ROLE_MANAGER], ""),
	(MANAGER_2, [ROLE_EMPLOYEE, ROLE_MANAGER], ""),
	(EMPLOYEE_1, [ROLE_EMPLOYEE], MANAGER_1),
	(EMPLOYEE_2, [ROLE_EMPLOYEE], MANAGER_1),
	(EMPLOYEE_3, [ROLE_EMPLOYEE], MANAGER_2),
	(EMPLOYEE_4, [ROLE_EMPLOYEE], EMPLOYEE_1),
	(HR, [ROLE_HR], None),
	(NO_RULE, [ROLE_NO_RULE], None),
	(ADMIN, ["System Manager"], None),
	(PORTAL, [ROLE_PORTAL], None),
	(DESK_ONLY, [ROLE_DESK_ONLY], None),
)
RECORD_OWNERS = (MANAGER_1, MANAGER_2, EMPLOYEE_1, EMPLOYEE_2, EMPLOYEE_3, EMPLOYEE_4)

# The record owners each user will see, by the union rule in section 3 of the decision note.
EXPECTED_VISIBLE = {
	EMPLOYEE_1: {EMPLOYEE_1},
	EMPLOYEE_2: {EMPLOYEE_2},
	EMPLOYEE_3: {EMPLOYEE_3},
	EMPLOYEE_4: {EMPLOYEE_4},
	MANAGER_1: {MANAGER_1, EMPLOYEE_1, EMPLOYEE_2, EMPLOYEE_4},
	MANAGER_2: {MANAGER_2, EMPLOYEE_3},
	HR: set(RECORD_OWNERS),
	NO_RULE: set(),
}

LEVEL_0 = {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "share": 1, "print": 1}


def ensure_roles() -> None:
	if not frappe.db.exists("Role", ROLE_PORTAL):
		frappe.get_doc(doctype="Role", role_name=ROLE_PORTAL, desk_access=0).insert()
	for role in (ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR, ROLE_NO_RULE, ROLE_DESK_ONLY):
		# Desk users: the shell lets a Website User call only its own short list of methods
		# (`kabuk/native_metadata.py`). The engine's surfaces under test are desk surfaces.
		if not frappe.db.exists("Role", role):
			frappe.get_doc(doctype="Role", role_name=role, desk_access=1).insert()
		elif not frappe.db.get_value("Role", role, "desk_access"):
			frappe.db.set_value("Role", role, "desk_access", 1)


REQUEST_ROLES = (ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR, ROLE_NO_RULE, ROLE_PORTAL, "System Manager")


def request_doctype(name: str, roles=REQUEST_ROLES, level_1_roles=(ROLE_HR, "System Manager")) -> dict:
	"""The definition of a made-up request type: an employee link and one field at level 1."""
	return {
		"doctype": "DocType",
		"name": name,
		"module": "Custom",
		"custom": 1,
		"autoname": "hash",
		"fields": [
			{"fieldname": "title", "fieldtype": "Data", "label": "Title", "description": "Short title."},
			{
				"fieldname": "employee",
				"fieldtype": "Link",
				"options": "Employee",
				"label": "Employee",
				"description": "Employee the request belongs to.",
			},
			{
				"fieldname": "department",
				"fieldtype": "Link",
				"options": "Department",
				"label": "Department",
				"description": "Department of the request.",
			},
			{
				"fieldname": "company",
				"fieldtype": "Link",
				"options": "Company",
				"label": "Company",
				"description": "Company of the request.",
			},
			{
				"fieldname": "status",
				"fieldtype": "Select",
				"options": "Open\nClosed",
				"default": "Open",
				"label": "Status",
				"description": "Open or closed.",
			},
			{
				"fieldname": "salary_amount",
				"fieldtype": "Currency",
				"label": "Salary Amount",
				"permlevel": 1,
				"description": "Sensitive amount. Only HR may read it.",
			},
		],
		"permissions": [{"role": role, **LEVEL_0} for role in roles]
		+ [{"role": role, "permlevel": 1, "read": 1, "write": 1} for role in level_1_roles],
	}


def ensure_doctypes() -> None:
	roles = REQUEST_ROLES
	if not frappe.db.exists("DocType", DOCTYPE):
		frappe.get_doc(request_doctype(DOCTYPE)).insert()
	if not frappe.db.exists("DocType", FREE_DOCTYPE):
		frappe.get_doc(
			doctype="DocType",
			name=FREE_DOCTYPE,
			module="Custom",
			custom=1,
			autoname="hash",
			fields=[
				{"fieldname": "title", "fieldtype": "Data", "label": "Title", "description": "Short title."}
			],
			permissions=[{"role": role, **LEVEL_0} for role in roles],
		).insert()


def ensure_portal_permission() -> None:
	"""A site made before the portal role existed gets the role's permission row here.

	The row is added to the document type itself. `add_permission` would copy every row to
	"Custom DocPerm", and the field level tests start from a type without such copies.
	"""
	doc = frappe.get_doc("DocType", DOCTYPE)
	if not any(row.role == ROLE_PORTAL for row in doc.permissions):
		doc.append("permissions", {"role": ROLE_PORTAL, **LEVEL_0})
		doc.save()


QUEUE_ROOM = 100


def run_queued_jobs(room: int = QUEUE_ROOM) -> int:
	"""Run the background jobs the test requests left behind, once enough of them wait.

	A test site has no worker. Requests still queue jobs, for example after a delete. Frappe
	refuses a new job once too many wait (`frappe/utils/background_jobs.py:729`), and then
	deletes and renames fail for a reason that has nothing to do with the test. A worker in
	burst mode runs what waits and stops. Returns the number of jobs that waited.
	"""
	waiting = sum(queue.count for queue in get_queues())
	if waiting >= room:
		subprocess.run(
			["bench", "worker", "--burst", "--quiet"],
			cwd=get_bench_path(),
			check=True,
			capture_output=True,
			timeout=600,
		)
	return waiting


def ensure_company() -> None:
	if not frappe.db.exists("Gender", GENDER):
		frappe.get_doc(doctype="Gender", gender=GENDER).insert()
	if not frappe.db.exists("Company", COMPANY):
		# The company row is written directly. The company setup of ERPNext creates a chart of accounts and warehouses.
		# That setup does not run on an empty test site and is not the subject of these tests.
		company = frappe.get_doc(
			doctype="Company", company_name=COMPANY, abbr="ERT", default_currency="TRY", country="Türkiye"
		)
		company.name = COMPANY
		company.db_insert()


def employee_of(user: str) -> str | None:
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def ensure_people() -> None:
	for email, roles, _manager in PEOPLE:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				doctype="User",
				email=email,
				first_name=email.split("@")[0],
				send_welcome_email=0,
				roles=[{"role": role} for role in roles],
			).insert()
			update_password(email, PASSWORD)
		elif frappe.db.get_value("User", email, "user_type") != "System User":
			# The user type follows the roles; saving works it out again.
			frappe.get_doc("User", email).save()
	for email, _roles, manager in PEOPLE:
		if manager is None or employee_of(email):
			continue
		frappe.get_doc(
			doctype="Employee",
			first_name=email.split("@")[0],
			company=COMPANY,
			status="Active",
			gender=GENDER,
			date_of_birth="1990-01-01",
			date_of_joining="2020-01-01",
			user_id=email,
			# ERPNext can create a “User Permission” record of its own for the employee. That record also narrows the records.
			# The tests check the engine alone. So that record is not created.
			create_user_permission=0,
			reports_to=employee_of(manager) if manager else None,
		).insert()
	frappe.db.delete("User Permission", {"user": ("in", [email for email, _roles, _manager in PEOPLE])})
	frappe.clear_cache()


def ensure_fixtures() -> None:
	"""Sets up the made-up roles, document types, company, users and employees once."""
	if not frappe.db.exists("DocType", "Employee"):
		raise RuntimeError("These tests need the Employee document type of ERPNext.")
	ensure_roles()
	ensure_doctypes()
	ensure_portal_permission()
	ensure_company()
	ensure_people()
	# Committed on purpose: the request uses another connection.
	frappe.db.commit()  # nosemgrep: frappe-request-commit


class ErisimTestCase(IntegrationTestCase):
	"""Each class sets up and deletes its own rules and records."""

	# A subclass can change this. The default rules are the P1 scenario of the roadmap.
	RULES = (
		{
			"title": "Calisan kendi kaydi",
			"role": ROLE_EMPLOYEE,
			"scope": "own",
			"match_field": "employee",
			"allow_read": 1,
			"allow_write": 1,
			"allow_create": 1,
			"priority": 10,
		},
		{
			"title": "Yonetici ekibi",
			"role": ROLE_MANAGER,
			"scope": "team",
			"match_field": "employee",
			"allow_read": 1,
			"priority": 20,
		},
		{
			"title": "IK tum kayitlar",
			"role": ROLE_HR,
			"scope": "all",
			"allow_read": 1,
			"allow_write": 1,
			"allow_create": 1,
			"allow_delete": 1,
			"priority": 30,
		},
	)

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_fixtures()
		run_queued_jobs()
		cls.site = frappe.local.site
		cls.rules = {}
		for rule in cls.RULES:
			doc = frappe.get_doc({"doctype": RULE_DOCTYPE, "document_type": DOCTYPE, "is_active": 1, **rule})
			cls.rules[rule["title"]] = doc.insert().name
		cls.records = {}
		for owner in RECORD_OWNERS:
			cls.records[owner] = cls.insert_record(owner)
		cls.owner_of = {name: owner for owner, name in cls.records.items()}
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("DocShare", {"share_doctype": DOCTYPE})
		frappe.db.delete(DOCTYPE)
		for name in frappe.get_all(RULE_DOCTYPE, pluck="name"):
			frappe.delete_doc(RULE_DOCTYPE, name, force=True)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	@classmethod
	def insert_record(cls, owner: str, **values) -> str:
		"""Creates the record as the administrator. The owner of the record is the employee in the `employee` field."""
		return (
			frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"title": f"Talep {owner}",
					"employee": employee_of(owner),
					"company": COMPANY,
					"status": "Open",
					"salary_amount": 1234,
					**values,
				}
			)
			.insert()
			.name
		)

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

	def login(self, user: str):
		"""Logs in on behalf of the user. The cookie stays in the client."""
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": PASSWORD})
		self.assertEqual(response.status_code, 200)
		return client

	def anonymous(self):
		return get_test_client(use_cookies=False)

	def api(self, client, method: str, endpoint: str, *, body=None, query=None):
		return self.send(client, method, API + endpoint, body=body, query=query)

	# --- data surfaces ---

	def rest_list(self, client, doctype: str = DOCTYPE, fields=("name",), filters=None):
		query = {"fields": json.dumps(list(fields)), "limit": 500}
		if filters:
			query["filters"] = json.dumps(filters)
		return self.send(client, "GET", REST + doctype, query=query)

	def listed_names(self, client, doctype: str = DOCTYPE) -> set[str]:
		response = self.rest_list(client, doctype)
		self.assertEqual(response.status_code, 200)
		return {row["name"] for row in response.json["data"]}

	def rest_get(self, client, name: str, doctype: str = DOCTYPE):
		return self.send(client, "GET", f"{REST}{doctype}/{name}")

	def rest_put(self, client, name: str, data: dict, doctype: str = DOCTYPE):
		return self.send(client, "PUT", f"{REST}{doctype}/{name}", body=data)

	def rest_post(self, client, data: dict, doctype: str = DOCTYPE):
		return self.send(client, "POST", REST + doctype, body=data)

	def rest_delete(self, client, name: str, doctype: str = DOCTYPE):
		return self.send(client, "DELETE", f"{REST}{doctype}/{name}")

	def readable_names(self, client) -> set[str]:
		"""The records for which the single record endpoint returns 200. The other records must return 403."""
		readable = set()
		for name in self.records.values():
			status = self.rest_get(client, name).status_code
			self.assertIn(status, (200, 403), name)
			if status == 200:
				readable.add(name)
		return readable

	def names_of(self, owners) -> set[str]:
		return {self.records[owner] for owner in owners}

	def assert_hidden(self, data: dict, fieldname: str) -> None:
		"""Frappe removes the value of a field without permission. In the response the field is either missing or empty."""
		self.assertFalse(data.get(fieldname), data)

	def stored(self, name: str, fieldname: str):
		return frappe.db.get_value(DOCTYPE, name, fieldname)
