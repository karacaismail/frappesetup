"""Shared parts of the four panel role tests (AJA-831, G-62, G-168, G-169, G-170).

The tests were written before the code (D-2). The expected results come from the decision site
and from the parent task AJA-827. Four roles are tested:

| Role                     | Frappe role              | Role Profile             |
| ------------------------ | ------------------------ | ------------------------ |
| Tenant admin             | "Tenant Admin"           | "Tenant Admin"           |
| Tenant admin assistant   | "Tenant Admin Assistant" | "Tenant Admin Assistant" |
| Reseller admin           | "Reseller Admin"         | "Reseller Admin"         |
| Reseller admin assistant | "Reseller Assistant"     | "Reseller Assistant"     |

Every holder is a "Website User". No role and no profile holds "System Manager".

Two kinds of tests use this file:

1. Setup tests read `setup/*.json`, `fixtures/*.json` and `hooks.py` only. They run without Frappe:
   `python3 -I -m unittest discover -s backend/apps/platform_core/platform_core/access/tests
   -t backend/apps/platform_core -p 'test_role_*.py'`
2. HTTP tests send requests through the WSGI application of Frappe (D-6). They run with
   `backend/dev/bin/test platform_core`. Without Frappe they are skipped.

Contract chosen by QA for the reseller tests (AJA-833 may change it with the PO):

- "Reseller Customer Link" has the fields `reseller_tenant` and `customer_tenant`.
- "Reseller Customer Request" has the fields `reseller_tenant`, `customer_name` and `contact_email`.
- A tenant is its own Frappe site. The reseller tenant of a request is the site that serves it.
- `list_customers` (GET) returns a list. Each row has `customer_tenant`.
- `customer_status` (GET, `customer_tenant`) returns `customer_tenant` and `status`.
- `request_customer` (POST, `customer_name`, `contact_email`) returns the `name` of the request.
- `approve_customer_request` (POST, `request`) approves one request.

All people and tenants are made up. Every address ends with `@example.test`.
"""

from __future__ import annotations

import ast
import importlib
import json
import unittest
from pathlib import Path

try:
	import frappe
	from frappe.tests import IntegrationTestCase
	from frappe.tests.test_api import make_request
	from frappe.utils import get_test_client
	from frappe.utils.password import update_password
except ImportError:  # The fixture tests also run without Frappe.
	frappe = None
	IntegrationTestCase = unittest.TestCase

APP_DIR = Path(__file__).resolve().parents[2]
FIXTURES_DIR = APP_DIR / "fixtures"
# AJA-899: the panel roles and profiles are not fixtures. The setup step opens the missing ones.
SETUP_DIR = APP_DIR / "setup"
SETUP_HOOK = "platform_core.setup.panel_roles.ensure"
HOOKS_FILE = APP_DIR / "hooks.py"

TENANT_ADMIN = "Tenant Admin"
TENANT_ADMIN_ASSISTANT = "Tenant Admin Assistant"
RESELLER_ADMIN = "Reseller Admin"
RESELLER_ASSISTANT = "Reseller Assistant"
PANEL_ROLES = (TENANT_ADMIN, TENANT_ADMIN_ASSISTANT, RESELLER_ADMIN, RESELLER_ASSISTANT)
PLATFORM_OPERATOR = "Platform Operator"
# No panel role and no panel profile may hold these roles.
PROTECTED_ROLES = ("System Manager", "Administrator")

LINK_DOCTYPE = "Reseller Customer Link"
REQUEST_DOCTYPE = "Reseller Customer Request"
RESELLER_API = "platform_core.api.reseller."
ACCESS_API = "platform_core.api.access."
METHOD = "/api/method/"
REST = "/api/v2/document/"
FAKE_LOGIN_TEXT = "Sahte-Parola-831-rol!"

# Made-up tenants. The test site is the reseller tenant of every request.
OWN_CUSTOMERS = ("musteri-a.example.test", "musteri-b.example.test")
OTHER_RESELLER = "baska-bayi.example.test"
OTHER_CUSTOMER = "musteri-c.example.test"
UNKNOWN_CUSTOMER = "olmayan-musteri.example.test"


# --- fixture files, read without Frappe ---


def load_fixture(name: str, folder: Path = FIXTURES_DIR) -> list[dict]:
	path = folder / name
	if not path.exists():
		return []
	return json.loads(path.read_text(encoding="utf-8"))


def load_setup(name: str) -> list[dict]:
	"""A data file of the setup step: `setup/role.json` or `setup/role_profile.json`."""
	return load_fixture(name, SETUP_DIR)


def hook_value(name: str) -> list:
	"""The literal value of a list in `hooks.py`. The last assignment wins, as in Python."""
	tree = ast.parse(HOOKS_FILE.read_text(encoding="utf-8"))
	value = []
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == name for target in node.targets
		):
			value = ast.literal_eval(node.value)
	return value


def hook_fixtures() -> list:
	return hook_value("fixtures")


def filter_matches(filters, name: str) -> bool:
	"""True if the fixture filters of `hooks.py` select the record with this name."""
	if not filters:
		return True
	for row in filters:
		if isinstance(row, dict):
			field, operator, value = "name", "=", row.get("name")
		elif len(row) == 3:
			field, operator, value = row
		else:
			_doctype, field, operator, value = row
		if field != "name":
			return False
		if operator == "=" and value != name:
			return False
		if operator == "in" and name not in value:
			return False
		if operator not in ("=", "in"):
			return False
	return True


def hook_exports(doctype: str, name: str) -> bool:
	for entry in hook_fixtures():
		if isinstance(entry, str):
			if entry == doctype:
				return True
			continue
		if entry.get("dt", entry.get("doctype")) == doctype and filter_matches(entry.get("filters"), name):
			return True
	return False


class RoleFixtureContract:
	"""Setup tests of one panel role. A subclass sets `ROLE`. No Frappe is needed.

	AJA-899: Frappe loads every file of `fixtures/` on each migrate and rewrites the record.
	A Role Profile write then leaves a lock (AJA-857). The roles and profiles are therefore
	set up by `platform_core.setup.panel_roles.ensure`, which opens only a missing record.
	"""

	ROLE = ""

	def role_record(self) -> dict | None:
		return next((row for row in load_setup("role.json") if row.get("name") == self.ROLE), None)

	def profile_record(self) -> dict | None:
		return next((row for row in load_setup("role_profile.json") if row.get("name") == self.ROLE), None)

	def test_role_is_set_up_without_desk_access(self):
		record = self.role_record()
		self.assertIsNotNone(record, f"setup/role.json has no {self.ROLE!r} role")
		self.assertEqual(record.get("role_name"), self.ROLE)
		# A role without desk access keeps its holder a Website User.
		self.assertEqual(record.get("desk_access"), 0)

	def test_role_and_profile_are_not_fixtures(self):
		self.assertFalse(hook_exports("Role", self.ROLE), f"hooks.py fixtures export {self.ROLE!r}")
		self.assertFalse(
			hook_exports("Role Profile", self.ROLE), f"hooks.py fixtures export the {self.ROLE!r} profile"
		)
		# Frappe loads every file of `fixtures/`, not only the exported ones.
		for name in ("role.json", "role_profile.json"):
			names = {row.get("name") for row in load_fixture(name)}
			self.assertNotIn(self.ROLE, names, f"fixtures/{name} still holds {self.ROLE!r}")

	def test_setup_step_runs_after_install_and_after_migrate(self):
		for hook in ("after_install", "after_migrate"):
			self.assertIn(SETUP_HOOK, hook_value(hook), hook)

	def test_role_profile_is_set_up_with_only_its_own_role(self):
		record = self.profile_record()
		self.assertIsNotNone(record, f"setup/role_profile.json has no {self.ROLE!r} profile")
		self.assertEqual(record.get("role_profile"), self.ROLE)
		self.assertEqual([row.get("role") for row in record.get("roles", [])], [self.ROLE])

	def test_no_system_manager_in_the_role_or_the_profile(self):
		record = self.profile_record()
		# A missing profile must not pass as a profile without “System Manager”.
		self.assertIsNotNone(record, f"setup/role_profile.json has no {self.ROLE!r} profile")
		self.assertIsNotNone(self.role_record(), f"setup/role.json has no {self.ROLE!r} role")
		roles = {row.get("role") for row in record.get("roles", [])}
		for protected in PROTECTED_ROLES:
			self.assertNotIn(protected, roles)
		self.assertNotIn(self.ROLE, PROTECTED_ROLES)
		# No role and no profile of the setup step may hold or be a protected role.
		for role in load_setup("role.json"):
			self.assertNotIn(role.get("name"), PROTECTED_ROLES)
		for profile in load_setup("role_profile.json"):
			held = {row.get("role") for row in profile.get("roles", [])}
			self.assertFalse(held & set(PROTECTED_ROLES), profile.get("name"))


# --- HTTP tests through the WSGI application of Frappe ---


def endpoint_exists(dotted: str) -> bool:
	module_name, _separator, attr = dotted.rpartition(".")
	try:
		function = getattr(importlib.import_module(module_name), attr)
	except (ImportError, AttributeError):
		return False
	return function in frappe.whitelisted


@unittest.skipIf(frappe is None, "Frappe is not installed: the HTTP tests run with backend/dev/bin/test")
class PanelRoleHttpCase(IntegrationTestCase):
	"""HTTP tests of one panel role. A subclass sets `ROLE`, `USER` and `FORBIDDEN_ROLES`."""

	ROLE = ""
	USER = ""
	# Roles the holder must never get through the profile.
	FORBIDDEN_ROLES: tuple[str, ...] = ()
	# Reseller tests set this: the made-up links of the own and of another reseller.
	MAKE_LINKS = False

	@classmethod
	def setUpClass(cls):
		if not cls.ROLE:
			raise unittest.SkipTest("The shared base has no role. Each role file subclasses it.")
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.site = frappe.local.site
		cls.remove_records()
		if cls.MAKE_LINKS:
			if not frappe.db.exists("DocType", LINK_DOCTYPE):
				raise AssertionError(f"The {LINK_DOCTYPE!r} type does not exist yet (AJA-833)")
			for customer in OWN_CUSTOMERS:
				cls.insert_link(cls.site, customer)
			cls.insert_link(OTHER_RESELLER, OTHER_CUSTOMER)
		if not frappe.db.exists("Role Profile", cls.ROLE):
			raise AssertionError(f"The {cls.ROLE!r} Role Profile does not exist yet (AJA-832)")
		cls.make_user(cls.USER, cls.ROLE)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		if not cls.ROLE:
			return
		frappe.set_user("Administrator")
		frappe.db.rollback()
		cls.remove_records()
		if frappe.db.exists("User", cls.USER):
			frappe.delete_doc("User", cls.USER, force=True, ignore_permissions=True)
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	@classmethod
	def remove_records(cls):
		for doctype in (LINK_DOCTYPE, REQUEST_DOCTYPE):
			if frappe.db.exists("DocType", doctype):
				frappe.db.delete(doctype)

	@classmethod
	def insert_link(cls, reseller: str, customer: str) -> str:
		doc = frappe.get_doc(doctype=LINK_DOCTYPE, reseller_tenant=reseller, customer_tenant=customer)
		return doc.insert(ignore_permissions=True).name

	@classmethod
	def insert_request(cls, reseller: str | None = None) -> str:
		"""Inserts a customer request as the administrator and commits it for the request."""
		doc = frappe.get_doc(
			doctype=REQUEST_DOCTYPE,
			reseller_tenant=reseller or cls.site,
			customer_name="Örnek Müşteri",
			contact_email="ornek.musteri@example.test",
		).insert(ignore_permissions=True)
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		return doc.name

	@classmethod
	def make_user(cls, email: str, profile: str) -> None:
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.get_doc(
			doctype="User",
			email=email,
			first_name=email.split("@")[0],
			send_welcome_email=0,
			role_profiles=[{"role_profile": profile}],
		).insert(ignore_permissions=True)
		update_password(email, FAKE_LOGIN_TEXT)

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def make_ai_records(self) -> dict[str, str]:
		"""Inserts the three AI records for one test and removes them after it (AJA-947)."""
		names = insert_ai_records(frappe.generate_hash(length=8))

		def remove():
			frappe.set_user("Administrator")
			frappe.db.rollback()
			remove_ai_records(names)
			# Committed on purpose: the request committed the records.
			frappe.db.commit()  # nosemgrep: frappe-request-commit

		self.addCleanup(remove)
		return names

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

	def login(self, user: str | None = None):
		client = get_test_client(use_cookies=True)
		response = self.send(
			client, "POST", "/api/method/login", body={"usr": user or self.USER, "pwd": FAKE_LOGIN_TEXT}
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		return client

	def call(self, client, http_method: str, dotted: str, **params):
		"""Calls a whitelisted method. GET sends the parameters as a query, POST as a body."""
		if http_method == "GET":
			return self.send(client, "GET", METHOD + dotted, query=params or None)
		return self.send(client, "POST", METHOD + dotted, body=params)

	def assert_denied(self, client, http_method: str, dotted: str, **params):
		"""The method exists and refuses the holder.

		The existence check keeps the test honest: a Website User gets 403 for every unknown
		method too. Without the check a missing endpoint would pass as a refusal.
		"""
		self.assertTrue(endpoint_exists(dotted), f"{dotted} is not a whitelisted method yet")
		response = self.call(client, http_method, dotted, **params)
		self.assertEqual(response.status_code, 403, (dotted, response.data[:300]))
		return response

	def assert_rest_denied(self, client, method: str, doctype: str, name: str | None = None, body=None):
		"""The document type exists and refuses the holder."""
		self.assertTrue(frappe.db.exists("DocType", doctype), f"{doctype} does not exist yet")
		path = REST + doctype + (f"/{name}" if name else "")
		response = self.send(client, method, path, body=body)
		self.assertEqual(response.status_code, 403, (method, path, response.data[:300]))
		return response

	# --- shared tests of every panel role ---

	def test_role_and_profile_exist_after_install(self):
		self.assertTrue(frappe.db.exists("Role", self.ROLE))
		self.assertEqual(frappe.db.get_value("Role", self.ROLE, "desk_access"), 0)
		self.assertTrue(frappe.db.exists("Role Profile", self.ROLE))
		roles = frappe.get_all(
			"Has Role", filters={"parenttype": "Role Profile", "parent": self.ROLE}, pluck="role"
		)
		self.assertEqual(roles, [self.ROLE])

	def test_holder_is_a_website_user_without_system_manager(self):
		user = frappe.get_doc("User", self.USER)
		roles = {row.role for row in user.roles}
		self.assertEqual(user.user_type, "Website User")
		self.assertIn(self.ROLE, roles)
		for role in (*PROTECTED_ROLES, *self.FORBIDDEN_ROLES):
			self.assertNotIn(role, roles)

	def test_holder_cannot_create_a_customer_link(self):
		client = self.login()
		body = {"reseller_tenant": self.site, "customer_tenant": "yeni-musteri.example.test"}
		self.assert_rest_denied(client, "POST", LINK_DOCTYPE, body=body)

	def test_holder_cannot_approve_a_customer_request(self):
		request = self.insert_request()
		before = frappe.db.get_value(REQUEST_DOCTYPE, request, "modified")

		self.assert_denied(self.login(), "POST", RESELLER_API + "approve_customer_request", request=request)

		self.assertEqual(frappe.db.get_value(REQUEST_DOCTYPE, request, "modified"), before)


# --- AI provider types (AJA-947) ---

# The panel page “Yapay zekâ sağlayıcıları” reads these three types.
AI_TYPES = ("PLT AI Provider", "PLT AI Account", "PLT AI API")
META_API = "platform_core.api.meta.get_doctype"
# A made-up credential. No response may carry it.
FAKE_AI_KEY = "sahte-anahtar-947-yalniz-test"


def insert_ai_records(suffix: str) -> dict[str, str]:
	"""Inserts one provider, account and API as the administrator. Returns the names by type."""
	provider = frappe.get_doc(
		doctype="PLT AI Provider", provider_name=f"PR Saglayici {suffix}", adapter="openai"
	).insert(ignore_permissions=True)
	account = frappe.get_doc(
		doctype="PLT AI Account",
		provider=provider.name,
		account_name=f"PR Hesap {suffix}",
		currency="USD",
	).insert(ignore_permissions=True)
	api = frappe.get_doc(
		doctype="PLT AI API",
		account=account.name,
		api_name=f"PR API {suffix}",
		base_url="https://saglayici.example.test",
		auth_type="api_key",
		api_key=FAKE_AI_KEY,
	).insert(ignore_permissions=True)
	return {"PLT AI Provider": provider.name, "PLT AI Account": account.name, "PLT AI API": api.name}


def remove_ai_records(names: dict[str, str]) -> None:
	for doctype in ("PLT AI API", "PLT AI Account", "PLT AI Provider"):
		name = names.get(doctype)
		if name and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
