"""Regression tests for the non-Python rule self-audit (docs/standartlar/frappe-python-disi-standartlari.md).

- W-1, L-3: the guest `/login` page escapes every value. Frappe 16 Jinja does not autoescape.
- W-8: the page has no inline script body; its script is a served asset.
- H-6: the two identity DocTypes deny portal users, and nobody creates or edits a deletion record.
- U-6, R-7: every site setting the module reads is documented in the README and in the contract.
- F-4: a Turkish Select description names the Turkish options, not the English option values.
- Y-11: real responses of the identity endpoints match the contract schemas.
"""

import ast
import csv
import os
import re
from unittest.mock import patch

import frappe
import yaml
from frappe.tests.test_api import FrappeAPITestCase
from jsonschema import Draft202012Validator

from platform_core.kimlik import provider_setup
from platform_core.kimlik.tests import helpers as h

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIMLIK = os.path.join(APP, "kimlik")
CONTRACT = os.path.join(APP, "..", "..", "..", "contracts", "platform_core-kimlik.openapi.yaml")
PORTAL_USER = "portal.kural.ornek@example.test"


def _contract() -> dict:
	with open(CONTRACT, encoding="utf-8") as handle:
		return yaml.safe_load(handle)


class TestWebRules(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = h.SiteSettings().__enter__()
		cls.addClassCleanup(cls.settings.__exit__, None, None, None)
		provider_setup.ensure_social_login_key()
		h.ensure_user(h.AYSE)
		h.refresh()
		cls.key = h.key()
		cls.patcher = h.jwks_patch(cls.key)
		cls.patcher.start()
		cls.addClassCleanup(cls.patcher.stop)

	def setUp(self):
		super().setUp()
		h.clear_links()
		h.reset_rate_limits()

	# --- W-1, L-3 -----------------------------------------------------------------------------------

	def test_login_page_escapes_the_brand_name(self):
		with h.SiteSettings({"kimlik_marka_adi": '<b>x</b>"'}):
			response = h.request(h.new_client().get, "/login", headers={"Accept-Language": "en"})
		self.assertEqual(response.status_code, 200)
		html = response.data.decode()
		self.assertNotIn("<b>x</b>", html)
		self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)

	def test_every_template_output_is_escaped(self):
		with open(os.path.join(APP, "www", "login.html"), encoding="utf-8") as handle:
			template = handle.read()
		for expression in re.findall(r"\{\{(.*?)\}\}", template, flags=re.S):
			self.assertRegex(expression.strip(), r"\|\s*(e|tojson)\s*$", expression.strip())

	# --- W-8 ----------------------------------------------------------------------------------------

	def test_login_page_has_no_inline_script(self):
		response = h.request(h.new_client().get, "/login", headers={"Accept-Language": "en"})
		html = response.data.decode()
		for attributes, body in re.findall(r"<script([^>]*)>(.*?)</script>", html, flags=re.S):
			self.assertIn("src=", attributes)
			self.assertEqual(body.strip(), "")
		self.assertTrue(os.path.exists(os.path.join(APP, "public", "kimlik", "login.js")))

	# --- H-6 ----------------------------------------------------------------------------------------

	def test_identity_doctypes_deny_portal_users(self):
		h.ensure_user(PORTAL_USER)
		h.make_link("sub-portal-kural", PORTAL_USER)
		client = h.new_client()
		h.login_with_keycloak(client, h.userinfo("sub-portal-kural", PORTAL_USER))
		for doctype in ("Platform Identity Link", "Platform Identity Deletion"):
			response = h.request(client.get, f"/api/resource/{doctype}")
			self.assertIn(response.status_code, (403,), f"{doctype}: {response.data[:160]}")

	def test_system_manager_cannot_create_or_edit_a_deletion_record(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		manager = "kural.yonetici@example.test"
		h.ensure_system_manager(manager, frappe.generate_hash(length=24))
		frappe.set_user(manager)
		doc = frappe.get_doc(
			{"doctype": "Platform Identity Deletion", "identity_hash": "b" * 64, "state": "Disabled"}
		)
		with self.assertRaises(frappe.PermissionError):
			doc.insert()
		frappe.set_user("Administrator")
		frappe.db.delete("Platform Identity Deletion", {"name": "b" * 64})

	# --- U-6, R-7 -----------------------------------------------------------------------------------

	def test_every_site_setting_is_documented(self):
		keys = set()
		for folder, _dirs, files in os.walk(KIMLIK):
			if f"{os.sep}tests" in folder:
				continue
			for name in files:
				if name.endswith(".py"):
					source = open(os.path.join(folder, name), encoding="utf-8").read()
					keys |= set(re.findall(r"conf\.get\(\s*\"([a-z_]+)\"", source))
					keys |= set(re.findall(r"conf\.([a-z_]+)\b(?!\()", source))
					for node in ast.walk(ast.parse(source)):
						if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
							target = node.targets[0]
							if isinstance(target, ast.Name) and target.id == "KEY_SETTING":
								keys.add(node.value.value)
		keys.discard("get")
		with open(os.path.join(KIMLIK, "README.md"), encoding="utf-8") as handle:
			readme = handle.read()
		documented = {entry["key"] for entry in _contract()["x-site-settings"]["settings"]}
		self.assertEqual(sorted(k for k in keys if f"`{k}`" not in readme), [])
		self.assertEqual(sorted(keys - documented), [])

	# --- F-4 ----------------------------------------------------------------------------------------

	def test_turkish_select_descriptions_use_turkish_options(self):
		with open(os.path.join(APP, "translations", "tr.csv"), encoding="utf-8", newline="") as handle:
			rows = {(r[0], r[2] if len(r) > 2 else ""): r[1] for r in csv.reader(handle) if r}
		for doctype in ("Platform Identity Link", "Platform Identity Deletion"):
			for field in frappe.get_meta(doctype).fields:
				if field.fieldtype != "Select" or not field.description:
					continue
				turkish = rows.get((field.description, doctype), "")
				for option in filter(None, (field.options or "").split("\n")):
					self.assertNotRegex(turkish, rf"\b{re.escape(option)}\b", f"{doctype}.{field.fieldname}")

	# --- Y-11 ---------------------------------------------------------------------------------------

	def test_real_identity_responses_match_the_contract(self):
		contract = _contract()

		def schema_of(path: str, method: str, status: str) -> dict:
			operation = contract["paths"][path][method]
			response = operation["responses"][status]
			if "$ref" in response:
				response = contract["components"]["responses"][response["$ref"].rsplit("/", 1)[1]]
			return response["content"]["application/json"]["schema"]

		def check(path: str, status: str, body: dict, method: str = "post"):
			schema = _resolve(schema_of(path, method, status), contract)
			Draft202012Validator(schema).validate(body)

		signed = self.key.sign(h.access_payload())
		headers = {"Authorization": f"Bearer {signed}"}
		body = {
			"issuer": h.ISSUER,
			"subject": "sub-sozlesme-kural",
			"email": "sozlesme.kural@example.test",
			"email_verified": True,
			"first_name": "Sozlesme",
			"last_name": "Kural",
			"enabled": True,
			"role_profiles": [],
		}
		self.addCleanup(
			frappe.delete_doc, "User", body["email"], force=True, ignore_permissions=True, ignore_missing=True
		)
		path = "/platform_core.api.identity.provision"
		ok = h.request(h.new_client().post, "/api/method" + path, json=body, headers=headers)
		self.assertEqual(ok.status_code, 200, ok.data[:200])
		check(path, "200", ok.json)
		missing = h.request(
			h.new_client().post, "/api/method" + path, json={"issuer": h.ISSUER}, headers=headers
		)
		self.assertEqual(missing.status_code, 400)
		check(path, "400", missing.json)
		path = "/platform_core.api.identity.set_enabled"
		unknown = h.request(
			h.new_client().post,
			"/api/method" + path,
			json={"issuer": h.ISSUER, "subject": "sub-yok-kural", "enabled": True},
			headers=headers,
		)
		self.assertEqual(unknown.status_code, 404)
		check(path, "404", unknown.json)

		path = "/platform_core.api.auth.setup_keycloak_login"
		admin = h.new_client()
		admin.set_cookie("sid", self.sid)
		setup = h.request(admin.post, "/api/method" + path, headers=h.csrf_headers(admin))
		self.assertEqual(setup.status_code, 200)
		check(path, "200", setup.json)

		path = "/platform_core.api.identity.list_identities"
		page = h.request(h.new_client().get, "/api/method" + path, headers=headers)
		self.assertEqual(page.status_code, 200, page.data[:200])
		check(path, "200", page.json, method="get")
		denied = h.request(h.new_client().get, "/api/method" + path)
		self.assertEqual(denied.status_code, 403)
		check(path, "403", denied.json, method="get")

	def test_callback_code_exchange_failure_matches_contract(self):
		client = h.new_client()
		started, query = h.start_login(client)
		self.assertEqual(started.status_code, 200)
		with patch("requests.post") as exchange:
			exchange.return_value.status_code = 400
			response = h.request(
				client.get,
				h.CALLBACK,
				query_string={"state": query["state"], "code": "rejected-example"},
			)
		self.assertEqual(response.status_code, 503)
		callback = _contract()["paths"]["/platform_core.api.auth.keycloak_callback"]["get"]
		self.assertIn(response.mimetype, callback["responses"]["503"]["content"])
		self.assertIn("code exchange failed", callback["responses"]["503"]["description"].lower())


def _resolve(node, contract):
	"""Inlines local `$ref` values, so a plain JSON Schema validator can check a response."""
	if isinstance(node, dict):
		if "$ref" in node and node["$ref"].startswith("#/"):
			target = contract
			for part in node["$ref"][2:].split("/"):
				target = target[part]
			merged = {k: v for k, v in node.items() if k != "$ref"}
			return _resolve({**target, **merged}, contract)
		return {k: _resolve(v, contract) for k, v in node.items()}
	if isinstance(node, list):
		return [_resolve(v, contract) for v in node]
	return node
