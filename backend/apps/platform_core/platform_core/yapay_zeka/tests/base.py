"""Yapay zekâ katmanı testlerinin ortak tabanı.

Testler isteği Frappe'nin WSGI uygulamasından geçirir (D-6). Böylece kimlik doğrulama,
HTTP yöntemi ve misafir denetimi gerçek yolda çalışır. Beklenen değerler
`contracts/platform_core-yapay-zeka.openapi.yaml` sözleşmesinden gelir (D-1).
"""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password

MCP_PATH = "/api/method/platform_core.api.ai.mcp"
API = "/api/method/platform_core.api.ai."
DOCTYPE = "YZ Test Kayit"
CHILD_DOCTYPE = "YZ Test Satir"
RESTRICTED_ROLE = "YZ Kisitli"
USER_A = "yz.a@example.test"
USER_B = "yz.b@example.test"
MANAGER = "yz.yonetici@example.test"
PASSWORD = "Sahte-Parola-7391-yz!"


def ensure_fixtures() -> None:
	"""Uydurma rol, kayıt türü ve kullanıcıları bir kez kurar."""
	if not frappe.db.exists("Role", RESTRICTED_ROLE):
		frappe.get_doc(doctype="Role", role_name=RESTRICTED_ROLE, desk_access=0).insert()
	if not frappe.db.exists("DocType", CHILD_DOCTYPE):
		frappe.get_doc(
			doctype="DocType",
			name=CHILD_DOCTYPE,
			module="Custom",
			custom=1,
			istable=1,
			fields=[
				{"fieldname": "item", "fieldtype": "Data", "label": "Item", "description": "Row text."},
				{
					"fieldname": "locked_note",
					"fieldtype": "Data",
					"label": "Locked Note",
					"permlevel": 1,
					"description": "Row note for managers only.",
				},
			],
		).insert()
	if frappe.db.exists("DocType", DOCTYPE) and not frappe.get_meta(DOCTYPE).has_field("rows"):
		# Eski test tanımı alt tablo taşımaz. Tanım yeniden kurulur.
		for name in frappe.get_all(DOCTYPE, pluck="name"):
			frappe.db.set_value(DOCTYPE, name, "docstatus", 0)
			frappe.delete_doc(DOCTYPE, name, force=True)
		frappe.delete_doc("DocType", DOCTYPE, force=True)
	if not frappe.db.exists("DocType", DOCTYPE):
		frappe.get_doc(
			doctype="DocType",
			name=DOCTYPE,
			module="Custom",
			custom=1,
			autoname="hash",
			is_submittable=1,
			track_changes=1,
			fields=[
				{"fieldname": "title", "fieldtype": "Data", "label": "Title", "description": "Short title."},
				{
					"fieldname": "amount",
					"fieldtype": "Int",
					"label": "Amount",
					"description": "Whole amount.",
				},
				{
					"fieldname": "internal_note",
					"fieldtype": "Data",
					"label": "Internal Note",
					"permlevel": 1,
					"description": "Note for managers only.",
				},
				{
					"fieldname": "vault_code",
					"fieldtype": "Password",
					"label": "Vault Code",
					"description": "A secret value.",
				},
				{
					"fieldname": "access_token",
					"fieldtype": "Data",
					"label": "Access Token",
					"description": "A secret kept in a plain field.",
				},
				{
					"fieldname": "rows",
					"fieldtype": "Table",
					"label": "Rows",
					"options": CHILD_DOCTYPE,
					"description": "Child rows of the record.",
				},
			],
			permissions=[
				{
					"role": RESTRICTED_ROLE,
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1,
					"submit": 1,
					"cancel": 1,
					"if_owner": 1,
				},
				{
					"role": "System Manager",
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1,
					"submit": 1,
					"cancel": 1,
					"report": 1,
				},
				{"role": "System Manager", "permlevel": 1, "read": 1, "write": 1},
			],
		).insert()
	for email, roles in (
		(USER_A, [RESTRICTED_ROLE]),
		(USER_B, [RESTRICTED_ROLE]),
		(MANAGER, ["System Manager"]),
	):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				doctype="User",
				email=email,
				first_name=email.split("@")[0],
				send_welcome_email=0,
				roles=[{"role": role} for role in roles],
			).insert()
			update_password(email, PASSWORD)
	frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır


class YzTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_fixtures()
		cls.site = frappe.local.site

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		# Log rows written by earlier tests or runs must not satisfy an assertion of this test.
		# Rows are told apart by name, not by time: the clock of the container host can step back.
		self.known_logs = set(frappe.get_all("AI Action Log", pluck="name"))

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		# Sonucu bilinmeyen öneri sonraki testin aynı hedefini kilitler. Test verisi temizlenir.
		frappe.db.delete("AI Action Proposal", {"result": "unknown"})
		frappe.db.commit()  # nosemgrep
		super().tearDown()

	# --- istek yardımcıları ---

	def send(self, client, method: str, path: str, *, body=None, headers=None, query=None):
		request_headers = {"Accept": "application/json"}
		if getattr(client, "csrf_token", None) and method != "GET":
			request_headers["X-Frappe-CSRF-Token"] = client.csrf_token
		kwargs = {"path": path, "method": method, "headers": request_headers}
		if body is not None:
			request_headers["Content-Type"] = "application/json"
			kwargs["data"] = json.dumps(body)
		if query:
			kwargs["query_string"] = query
		request_headers.update(headers or {})
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır
		try:
			return make_request(client.open, args=(), kwargs=kwargs, site=self.site)
		finally:
			frappe.db.rollback()

	def login(self, user: str, *, csrf: bool = True):
		"""Kullanıcı adına oturum açar. Çerez istemcide kalır.

		Panel sayfası oturuma CSRF belirteci koyar ve tarayıcı onu başlıkta gönderir.
		Test aynı durumu kurar: belirteci oturuma yazar ve her yazan istekte gönderir.
		"""
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": PASSWORD})
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		if csrf:
			sid = client.get_cookie("sid").value
			session = frappe.cache.hget("session", sid)
			session["data"]["csrf_token"] = frappe.generate_hash()
			frappe.cache.hset("session", sid, session)
			client.csrf_token = session["data"]["csrf_token"]
		return client

	def anonymous(self):
		return get_test_client(use_cookies=False)

	def issue_token(self, client) -> str:
		response = self.send(client, "POST", API + "issue_agent_token", body={})
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["message"]["token"]

	def rpc(self, client, method: str, params=None, *, token=None, headers=None, request_id=1):
		payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
		if params is not None:
			payload["params"] = params
		request_headers = dict(headers or {})
		if token:
			request_headers["Authorization"] = f"Bearer {token}"
		return self.send(client, "POST", MCP_PATH, body=payload, headers=request_headers)

	def call_tool(self, client, name: str, arguments: dict, *, token=None) -> dict:
		"""Aracı çağırır ve MCP araç sonucunu döner."""
		response = self.rpc(client, "tools/call", {"name": name, "arguments": arguments}, token=token)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		self.assertIn("result", response.json, response.json)
		return response.json["result"]

	def assert_denied(self, result: dict, code: str) -> None:
		self.assertTrue(result["isError"], result)
		self.assertEqual(result["structuredContent"]["error"]["code"], code, result)

	def human(self, client, method: str, endpoint: str, body=None, query=None):
		return self.send(client, method, API + endpoint, body=body, query=query)

	def open_report_gate(self) -> None:
		"""Install a report gate that allows every report, for tests about other report rules.

		The real gate is `platform_core.erisim.reports.guard`. Without it the report tool is closed.
		"""
		import sys
		from types import ModuleType
		from unittest.mock import patch

		module = ModuleType("platform_core.erisim.reports")
		module.guard = lambda report_name, user=None: None
		patcher = patch.dict(sys.modules, {"platform_core.erisim.reports": module})
		patcher.start()
		self.addCleanup(patcher.stop)

	def in_other_connection(self, action) -> None:
		"""Run `action` and commit it on a separate database connection, as another request would."""
		from threading import Thread

		site = self.site

		def run():
			frappe.init(site)
			frappe.connect()
			try:
				action()
				frappe.db.commit()  # nosemgrep
			finally:
				frappe.destroy()

		thread = Thread(target=run)
		thread.start()
		thread.join()

	# --- veri yardımcıları ---

	def make_record(self, owner: str, **values) -> str:
		frappe.set_user(owner)
		try:
			doc = frappe.get_doc({"doctype": DOCTYPE, "title": "Ornek", "amount": 10, **values}).insert()
		finally:
			frappe.set_user("Administrator")
		frappe.db.commit()  # nosemgrep: istek ayrı bağlantı kullanır
		self.addCleanup(self.drop_record, doc.name)
		return doc.name

	def drop_record(self, name: str) -> None:
		frappe.set_user("Administrator")
		if frappe.db.exists(DOCTYPE, name):
			if frappe.db.get_value(DOCTYPE, name, "docstatus") == 1:
				frappe.get_doc(DOCTYPE, name).cancel()
			frappe.delete_doc(DOCTYPE, name, force=True)
		frappe.db.commit()  # nosemgrep

	def last_log(self, **filters) -> dict | None:
		"""Return the newest log row this test wrote that matches the filters."""
		names = [
			name
			for name in frappe.get_all("AI Action Log", filters=filters, pluck="name")
			if name not in self.known_logs
		]
		if not names:
			return None
		rows = frappe.get_all(
			"AI Action Log",
			filters={"name": ("in", names)},
			fields=["*"],
			order_by="creation desc, name desc",
			limit=1,
		)
		return rows[0]

	def propose_update(self, client, name: str, **data) -> dict:
		result = self.call_tool(client, "update_document", {"doctype": DOCTYPE, "name": name, "data": data})
		self.assertFalse(result["isError"], result)
		return result["structuredContent"]

	def digest_of(self, client, proposal_id: str) -> str:
		response = self.human(client, "GET", "get_proposal", query={"proposal_id": proposal_id})
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return response.json["message"]["digest"]

	def approve(self, client, proposal_id: str, digest: str | None = None):
		digest = digest or self.digest_of(client, proposal_id)
		return self.human(
			client, "POST", "approve_proposal", body={"proposal_id": proposal_id, "digest": digest}
		)
