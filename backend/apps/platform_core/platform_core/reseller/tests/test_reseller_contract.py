"""Static contract of the reseller records and endpoints (G-169, G-170, AJA-833).

Written before the code (D-2). The static tests read files only. Runtime pagination tests additionally need Frappe:
`python3 -I -m unittest discover -s backend/apps/platform_core/platform_core/reseller/tests
-t backend/apps/platform_core -p 'test_reseller_contract.py'`
"""

from __future__ import annotations

import ast
import json
import unittest
from importlib.util import find_spec
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

APP_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = APP_DIR.parents[2]
DOCTYPE_DIR = APP_DIR / "reseller" / "doctype"
API_FILE = APP_DIR / "api" / "reseller.py"
CONTRACT_FILE = BACKEND_DIR / "contracts" / "platform_core-reseller.openapi.yaml"

LINK = "Reseller Customer Link"
REQUEST = "Reseller Customer Request"
OPERATOR = "Platform Operator"
RESELLER_ROLES = ("Reseller Admin", "Reseller Assistant")
PANEL_ROLES = ("Tenant Admin", "Tenant Admin Assistant", *RESELLER_ROLES)
ENDPOINTS = ("list_customers", "customer_status", "request_customer", "approve_customer_request")
# The endpoints a reseller calls. A reseller is a Website User, so they must be allow-listed.
RESELLER_ENDPOINTS = ("list_customers", "customer_status", "request_customer")
# Money terms stay with the project owner (G-169). No record holds them.
MONEY_WORDS = ("price", "discount", "commission", "rate", "amount", "fee")


def doctype(name: str) -> dict:
	folder = name.lower().replace(" ", "_")
	path = DOCTYPE_DIR / folder / f"{folder}.json"
	if not path.exists():
		raise AssertionError(f"{path.relative_to(APP_DIR)} does not exist yet")
	return json.loads(path.read_text(encoding="utf-8"))


def hook_value(name: str):
	tree = ast.parse((APP_DIR / "hooks.py").read_text(encoding="utf-8"))
	value = None
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == name for target in node.targets
		):
			value = ast.literal_eval(node.value)
	return value


def whitelisted_functions() -> dict[str, list[str]]:
	"""Function name -> allowed HTTP methods of every `@frappe.whitelist` function in the API file."""
	if not API_FILE.exists():
		raise AssertionError("platform_core/api/reseller.py does not exist yet")
	found = {}
	for node in ast.parse(API_FILE.read_text(encoding="utf-8")).body:
		if not isinstance(node, ast.FunctionDef):
			continue
		for decorator in node.decorator_list:
			if isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "frappe.whitelist":
				methods = next((kw.value for kw in decorator.keywords if kw.arg == "methods"), None)
				found[node.name] = ast.literal_eval(methods) if methods is not None else []
	return found


class TestResellerDoctypes(unittest.TestCase):
	def test_link_has_the_two_tenant_fields(self):
		fields = {row["fieldname"]: row for row in doctype(LINK)["fields"]}
		for name in ("reseller_tenant", "customer_tenant", "site_status"):
			self.assertIn(name, fields)
			self.assertEqual(fields[name].get("reqd"), 1, name)
		# One customer tenant belongs to one reseller only.
		self.assertEqual(fields["customer_tenant"].get("unique"), 1)

	def test_request_has_the_contact_fields_and_a_status(self):
		fields = {row["fieldname"]: row for row in doctype(REQUEST)["fields"]}
		for name in ("reseller_tenant", "customer_name", "contact_email", "status"):
			self.assertIn(name, fields)
		self.assertEqual(fields["status"]["options"].split("\n"), ["Pending", "Approved"])
		self.assertEqual(fields["status"].get("default"), "Pending")

	def test_only_the_platform_operator_writes_the_records(self):
		for name in (LINK, REQUEST):
			permissions = doctype(name)["permissions"]
			roles = {row["role"] for row in permissions}
			self.assertIn(OPERATOR, roles, name)
			# Panel roles get no document permission. They use the endpoints only.
			self.assertFalse(roles & set(PANEL_ROLES), name)
			for row in permissions:
				self.assertIn(row["role"], (OPERATOR, "System Manager"), name)

	def test_every_field_has_a_description(self):
		for name in (LINK, REQUEST):
			data = doctype(name)
			self.assertTrue(data.get("description"), name)
			self.assertEqual(data.get("module"), "Reseller")
			for field in data["fields"]:
				self.assertTrue(field.get("description"), (name, field["fieldname"]))

	def test_no_money_field(self):
		for name in (LINK, REQUEST):
			for field in doctype(name)["fields"]:
				for word in MONEY_WORDS:
					self.assertNotIn(word, field["fieldname"], (name, field["fieldname"]))

	def test_the_module_is_registered(self):
		modules = (APP_DIR / "modules.txt").read_text(encoding="utf-8").split()
		self.assertIn("Reseller", modules)


class TestResellerEndpoints(unittest.TestCase):
	def test_the_four_endpoints_exist_with_their_methods(self):
		functions = whitelisted_functions()
		self.assertEqual(set(functions), set(ENDPOINTS))
		self.assertEqual(functions["list_customers"], ["GET"])
		self.assertEqual(functions["customer_status"], ["GET"])
		self.assertEqual(functions["request_customer"], ["POST"])
		self.assertEqual(functions["approve_customer_request"], ["POST"])

	def test_reseller_endpoints_are_on_the_website_user_list(self):
		allowed = hook_value("website_user_allowed_methods")
		for name in RESELLER_ENDPOINTS:
			self.assertIn(f"platform_core.api.reseller.{name}", allowed)
		# The operator works in Desk. Its endpoint stays off the Website User list.
		self.assertNotIn("platform_core.api.reseller.approve_customer_request", allowed)

	def test_platform_operator_is_a_desk_role_of_the_setup_step(self):
		# AJA-899: the role is not a fixture. The setup step opens it only when it is missing.
		roles = json.loads((APP_DIR / "setup" / "role.json").read_text(encoding="utf-8"))
		record = next((row for row in roles if row.get("name") == OPERATOR), None)
		self.assertIsNotNone(record, "setup/role.json has no Platform Operator role")
		self.assertEqual(record.get("desk_access"), 1)
		for entry in hook_value("fixtures"):
			if isinstance(entry, dict) and entry.get("dt") == "Role":
				self.assertNotIn(OPERATOR, json.dumps(entry.get("filters")))
		fixture = APP_DIR / "fixtures" / "role.json"
		if fixture.exists():
			names = {row.get("name") for row in json.loads(fixture.read_text(encoding="utf-8"))}
			self.assertNotIn(OPERATOR, names)
		# No panel profile holds the operator role.
		profiles = json.loads((APP_DIR / "setup" / "role_profile.json").read_text(encoding="utf-8"))
		for profile in profiles:
			self.assertNotIn(OPERATOR, {row.get("role") for row in profile.get("roles", [])})

	def test_the_contract_names_every_endpoint(self):
		self.assertTrue(CONTRACT_FILE.exists(), "the reseller OpenAPI contract does not exist yet")
		text = CONTRACT_FILE.read_text(encoding="utf-8")
		for name in ENDPOINTS:
			self.assertIn(f"/platform_core.api.reseller.{name}:", text)

	def test_customer_page_contract(self):
		contract = yaml.safe_load(CONTRACT_FILE.read_text())
		operation = contract["paths"]["/platform_core.api.reseller.list_customers"]["get"]
		params = {p["name"]: p["schema"] for p in operation["parameters"]}
		self.assertEqual(params["offset"]["minimum"], 0)
		self.assertEqual(params["offset"]["default"], 0)
		self.assertEqual(params["page_size"]["minimum"], 1)
		self.assertEqual(params["page_size"]["default"], 50)
		self.assertIn("417", operation["responses"])
		schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
		page = schema["properties"]["message"]
		self.assertEqual(page["type"], "object")
		self.assertEqual(set(page["required"]), {"items", "has_more", "offset", "page_size"})
		self.assertEqual(page["properties"]["items"]["maxItems"], 100)
		self.assertEqual(page["properties"]["has_more"]["type"], "boolean")
		self.assertEqual(page["properties"]["page_size"]["maximum"], 100)


@unittest.skipIf(find_spec("frappe") is None, "Runtime tests need Frappe installed.")
class TestCustomerPages(unittest.TestCase):
	def setUp(self):
		from platform_core.reseller import customers

		self.customers = customers
		self.rows = [
			SimpleNamespace(
				customer_tenant=f"customer-{i:03d}",
				customer_name=None,
				site_status="Active",
				reseller_tenant="own-site",
			)
			for i in range(205)
		]
		self.rows.append(
			SimpleNamespace(
				customer_tenant="foreign",
				customer_name=None,
				site_status="Active",
				reseller_tenant="other-site",
			)
		)
		self.queries = []

		def listed(doctype, **kwargs):
			self.queries.append(kwargs)
			rows = [r for r in self.rows if r.reseller_tenant == kwargs["filters"]["reseller_tenant"]]
			offset = kwargs.get("limit_start", 0)
			limit = kwargs.get("limit_page_length", 0)
			return rows[offset : offset + limit] if limit else rows[offset:]

		self.patch = patch.object(
			customers,
			"frappe",
			SimpleNamespace(
				get_roles=lambda: ["Reseller Admin"], local=SimpleNamespace(site="own-site"), get_all=listed
			),
		)
		self.patch.start()
		self.addCleanup(self.patch.stop)

	def test_default_page_is_bounded_and_has_more(self):
		page = self.customers.list_customers()
		self.assertEqual(len(page["items"]), 50)
		self.assertEqual(page["page_size"], 50)
		self.assertTrue(page["has_more"])
		self.assertLessEqual(self.queries[0]["limit_page_length"], 101)

	def test_large_page_is_clamped_and_all_pages_preserve_tenant_scope(self):
		seen = []
		for offset, size, more in ((0, 100, True), (100, 100, True), (200, 5, False), (205, 0, False)):
			page = self.customers.list_customers(offset=offset, page_size=999999)
			self.assertEqual(page["offset"], offset)
			self.assertEqual(page["page_size"], 100)
			self.assertEqual(page["has_more"], more)
			self.assertEqual(len(page["items"]), size)
			seen.extend(row["customer_tenant"] for row in page["items"])
		self.assertEqual(seen, [f"customer-{i:03d}" for i in range(205)])
		self.assertTrue(all(q["limit_page_length"] == 101 for q in self.queries))

	def test_exact_full_page_has_no_next_page(self):
		page = self.customers.list_customers(offset=105, page_size=100)
		self.assertEqual(len(page["items"]), 100)
		self.assertFalse(page["has_more"])


if __name__ == "__main__":
	unittest.main()
