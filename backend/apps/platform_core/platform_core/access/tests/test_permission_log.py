"""G-62 and G-98: the “Tenant Admin” reads the Permission Log of its own site (AJA-791).

Frappe writes a Permission Log row when a role profile changes. The holder makes a profile through
the document route, then reads the row through the endpoint. The expected fields come from the
contract (`contracts/platform_core-access.openapi.yaml`) (D-1). All people are made up.
"""

import json
from urllib.parse import quote

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password

from platform_core.access import tenant_admin
from platform_core.access.tests.base import PASSWORD

API = "/api/method/platform_core.api.access."
HOLDER = "pl.yonetici@example.test"
PLAIN = "pl.uye@example.test"
PLAIN_ROLE = "PL Deneme Rol"
PROFILE = "PL Deneme Profil"
FIELDS = {
	"name",
	"changed_at",
	"changed_by",
	"for_doctype",
	"for_document",
	"reference_type",
	"reference",
	"status",
	"changes",
}


def _user(email: str, roles: list[str]) -> None:
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			doctype="User",
			email=email,
			first_name=email.split("@")[0],
			send_welcome_email=0,
			roles=[{"role": role} for role in roles],
		).insert(ignore_permissions=True)
	update_password(email, PASSWORD)


class TestPermissionLog(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site = frappe.local.site
		frappe.set_user("Administrator")
		# An interrupted run can leave the profile and its log rows behind.
		cls.clean()
		# The setup step makes the role on install. This call adds its permission rows.
		tenant_admin.ensure_permissions()
		if not frappe.db.exists("Role", PLAIN_ROLE):
			frappe.get_doc(doctype="Role", role_name=PLAIN_ROLE, desk_access=0).insert()
		_user(HOLDER, [tenant_admin.ROLE])
		_user(PLAIN, [PLAIN_ROLE])
		frappe.db.commit()  # nosemgrep: frappe-test-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.clean()
		frappe.db.commit()  # nosemgrep: frappe-test-commit
		super().tearDownClass()

	@staticmethod
	def clean():
		if frappe.db.exists("Role Profile", PROFILE):
			frappe.delete_doc("Role Profile", PROFILE, ignore_permissions=True, force=True)
		# The rows of an earlier run would be counted with the row of this run.
		frappe.db.delete("Permission Log", {"for_doctype": "Role Profile", "for_document": PROFILE})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self.clean()
		frappe.db.commit()  # nosemgrep: frappe-test-commit
		super().tearDown()

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

	def login(self, user: str = HOLDER):
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": PASSWORD})
		self.assertEqual(response.status_code, 200)
		return client

	def logs(self, client, **query):
		return self.send(client, "GET", API + "list_permission_logs", query=query or None)

	def test_holder_reads_the_log_row_of_its_own_change(self):
		client = self.login()
		made = self.send(
			client,
			"POST",
			"/api/resource/" + quote("Role Profile"),
			body={"role_profile": PROFILE, "roles": [{"role": PLAIN_ROLE}]},
		)
		self.assertEqual(made.status_code, 200, made.data[:500])
		response = self.logs(client, for_doctype="Role Profile", for_document=PROFILE)
		self.assertEqual(response.status_code, 200, response.data[:500])
		message = response.json["message"]
		self.assertEqual(len(message["logs"]), 1, message)
		row = message["logs"][0]
		self.assertEqual(set(row), FIELDS)
		self.assertEqual(row["changed_by"], HOLDER)
		self.assertEqual(row["status"], "Added")
		self.assertIsInstance(row["changes"], dict)
		self.assertIs(message["has_more"], False)

	def test_pages_are_bounded(self):
		client = self.login()
		response = self.logs(client, page_length=1)
		self.assertEqual(response.status_code, 200, response.data[:500])
		self.assertLessEqual(len(response.json["message"]["logs"]), 1)
		for bad in ({"page_length": 0}, {"page_length": 101}, {"start": -1}, {"page_length": "x"}):
			self.assertEqual(self.logs(client, **bad).status_code, 400, bad)

	def test_unknown_query_field_is_refused(self):
		client = self.login()
		self.assertEqual(self.logs(client, changed_by=HOLDER).status_code, 400)

	def test_plain_user_cannot_read_the_log(self):
		client = self.login(PLAIN)
		self.assertEqual(self.logs(client).status_code, 403)
		# The document route of the type stays closed too.
		response = self.send(client, "GET", "/api/resource/" + quote("Permission Log"))
		self.assertEqual(response.status_code, 403)

	def test_post_is_refused(self):
		client = self.login()
		response = self.send(client, "POST", API + "list_permission_logs", body={})
		self.assertNotEqual(response.status_code, 200)
