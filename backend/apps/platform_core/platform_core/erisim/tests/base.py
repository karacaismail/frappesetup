"""Erişim kuralı testlerinin ortak tabanı.

Testler isteği Frappe'nin WSGI uygulamasından geçirir (D-6). Böylece oturum, HTTP yöntemi
ve izin kancaları gerçek yolda çalışır. Beklenen sonuçlar karar notundan
(`docs/kararlar/0006-erisim-kurali.md`), sözleşmeden
(`contracts/platform_core-erisim.openapi.yaml`) ve karar sitesinin G-60, G-61 ve G-121
maddelerinden gelir (D-1). Bütün kişiler ve kayıtlar uydurmadır.

Örnek ağaç:

    yonetici1 ── calisan1 ── calisan4
              └─ calisan2
    yonetici2 ── calisan3
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
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

EMPLOYEE_1 = "er.calisan1@example.test"
EMPLOYEE_2 = "er.calisan2@example.test"
EMPLOYEE_3 = "er.calisan3@example.test"
EMPLOYEE_4 = "er.calisan4@example.test"
MANAGER_1 = "er.yonetici1@example.test"
MANAGER_2 = "er.yonetici2@example.test"
HR = "er.ik@example.test"
NO_RULE = "er.kuralsiz@example.test"
ADMIN = "er.admin@example.test"

# Kullanıcı, roller ve bağlı olduğu yönetici. `None` çalışan kaydı olmadığını gösterir.
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
)
RECORD_OWNERS = (MANAGER_1, MANAGER_2, EMPLOYEE_1, EMPLOYEE_2, EMPLOYEE_3, EMPLOYEE_4)

# Karar notunun 3. bölümündeki birleşim kuralına göre her kullanıcının göreceği kayıt sahipleri.
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
	for role in (ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR, ROLE_NO_RULE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc(doctype="Role", role_name=role, desk_access=0).insert()


def ensure_doctypes() -> None:
	roles = (ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_HR, ROLE_NO_RULE, "System Manager")
	if not frappe.db.exists("DocType", DOCTYPE):
		frappe.get_doc(
			doctype="DocType",
			name=DOCTYPE,
			module="Custom",
			custom=1,
			autoname="hash",
			fields=[
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
			permissions=[{"role": role, **LEVEL_0} for role in roles]
			+ [
				{"role": ROLE_HR, "permlevel": 1, "read": 1, "write": 1},
				{"role": "System Manager", "permlevel": 1, "read": 1, "write": 1},
			],
		).insert()
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


def ensure_company() -> None:
	if not frappe.db.exists("Gender", GENDER):
		frappe.get_doc(doctype="Gender", gender=GENDER).insert()
	if not frappe.db.exists("Company", COMPANY):
		# Şirket satırı doğrudan yazılır. ERPNext'in şirket kurulumu hesap planı ve depo açar.
		# O kurulum boş test sitesinde çalışmaz ve bu testlerin konusu değildir.
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
			# ERPNext çalışana kendi “User Permission” kaydını açabilir. O kayıt da kayıtları daraltır.
			# Testler motoru tek başına sınar. Bu yüzden o kayıt açılmaz.
			create_user_permission=0,
			reports_to=employee_of(manager) if manager else None,
		).insert()
	frappe.db.delete("User Permission", {"user": ("in", [email for email, _roles, _manager in PEOPLE])})
	frappe.clear_cache()


def ensure_fixtures() -> None:
	"""Uydurma rolleri, kayıt türlerini, şirketi, kullanıcıları ve çalışanları bir kez kurar."""
	if not frappe.db.exists("DocType", "Employee"):
		raise RuntimeError("Bu testler ERPNext'in Employee kayıt türünü ister.")
	ensure_roles()
	ensure_doctypes()
	ensure_company()
	ensure_people()
	frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır


class ErisimTestCase(IntegrationTestCase):
	"""Her sınıf kendi kurallarını ve kayıtlarını kurar ve siler."""

	# Alt sınıf değiştirebilir. Varsayılan kurallar yol haritasının P1 senaryosudur.
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
		cls.site = frappe.local.site
		cls.rules = {}
		for rule in cls.RULES:
			doc = frappe.get_doc({"doctype": RULE_DOCTYPE, "document_type": DOCTYPE, "is_active": 1, **rule})
			cls.rules[rule["title"]] = doc.insert().name
		cls.records = {}
		for owner in RECORD_OWNERS:
			cls.records[owner] = cls.insert_record(owner)
		cls.owner_of = {name: owner for owner, name in cls.records.items()}
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("DocShare", {"share_doctype": DOCTYPE})
		frappe.db.delete(DOCTYPE)
		for name in frappe.get_all(RULE_DOCTYPE, pluck="name"):
			frappe.delete_doc(RULE_DOCTYPE, name, force=True)
		frappe.db.commit()  # nosemgrep
		super().tearDownClass()

	@classmethod
	def insert_record(cls, owner: str, **values) -> str:
		"""Kaydı yönetici olarak açar. Kaydın sahibi `employee` alanındaki çalışandır."""
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

	# --- istek yardımcıları ---

	def send(self, client, method: str, path: str, *, body=None, query=None):
		headers = {"Accept": "application/json"}
		kwargs = {"path": path, "method": method, "headers": headers}
		if body is not None:
			headers["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		if query:
			kwargs["query_string"] = query
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def login(self, user: str):
		"""Kullanıcı adına oturum açar. Çerez istemcide kalır."""
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": PASSWORD})
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return client

	def anonymous(self):
		return get_test_client(use_cookies=False)

	def api(self, client, method: str, endpoint: str, *, body=None, query=None):
		return self.send(client, method, API + endpoint, body=body, query=query)

	# --- veri yüzeyleri ---

	def rest_list(self, client, doctype: str = DOCTYPE, fields=("name",), filters=None):
		query = {"fields": json.dumps(list(fields)), "limit": 500}
		if filters:
			query["filters"] = json.dumps(filters)
		return self.send(client, "GET", REST + doctype, query=query)

	def listed_names(self, client, doctype: str = DOCTYPE) -> set[str]:
		response = self.rest_list(client, doctype)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
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
		"""Tek kayıt ucunun 200 döndüğü kayıtlar. Öteki kayıtlar 403 dönmelidir."""
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
		"""Frappe izinsiz alanın değerini siler. Yanıtta alan ya yoktur ya da boştur."""
		self.assertFalse(data.get(fieldname), data)

	def stored(self, name: str, fieldname: str):
		return frappe.db.get_value(DOCTYPE, name, fieldname)
