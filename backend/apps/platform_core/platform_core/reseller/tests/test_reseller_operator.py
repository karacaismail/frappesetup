"""HTTP tests of the operator side of the reseller endpoints (G-169, G-170, AJA-833).

Written before the code (D-2). The reseller side is tested in `access/tests/test_role_reseller_*.py`.
These tests add the operator side and the input checks. They send real requests through the
WSGI application of Frappe (D-6) and run with `backend/dev/bin/test platform_core`.

All people and tenants are made up. Every address ends with `@example.test`.
"""

from __future__ import annotations

import json
import unittest

try:
	import frappe
	from frappe.tests import IntegrationTestCase
	from frappe.tests.test_api import make_request
	from frappe.utils import get_test_client
	from frappe.utils.password import update_password
except ImportError:
	frappe = None
	IntegrationTestCase = unittest.TestCase

LINK = "Reseller Customer Link"
REQUEST = "Reseller Customer Request"
API = "/api/method/platform_core.api.reseller."
REST = "/api/v2/document/"
FAKE_LOGIN_TEXT = "Sahte-Parola-833-bayi!"
OPERATOR = "pr.operator.833@example.test"
RESELLER = "pr.bayi.833@example.test"
TENANT_ADMIN = "pr.kiraci.833@example.test"
CUSTOMER = "musteri-833.example.test"


@unittest.skipIf(frappe is None, "Frappe is not installed: the HTTP tests run with backend/dev/bin/test")
class TestResellerOperatorHttp(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.site = frappe.local.site
		cls.clean()
		cls.make_user(OPERATOR, roles=["Platform Operator"])
		cls.make_user(RESELLER, profile="Reseller Admin")
		cls.make_user(TENANT_ADMIN, profile="Tenant Admin")
		# Committed on purpose: the request uses another connection.
		frappe.db.commit()  # nosemgrep: frappe-request-commit

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		cls.clean()
		# Committed on purpose: other connections must see this.
		frappe.db.commit()  # nosemgrep: frappe-request-commit
		super().tearDownClass()

	@classmethod
	def clean(cls):
		for doctype in (LINK, REQUEST):
			if frappe.db.exists("DocType", doctype):
				frappe.db.delete(doctype)
		for user in (OPERATOR, RESELLER, TENANT_ADMIN):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)

	@classmethod
	def make_user(cls, email: str, roles=(), profile: str | None = None) -> None:
		doc = frappe.get_doc(
			doctype="User",
			email=email,
			first_name=email.split("@")[0],
			send_welcome_email=0,
			roles=[{"role": role} for role in roles],
			role_profiles=[{"role_profile": profile}] if profile else [],
		)
		doc.insert(ignore_permissions=True)
		update_password(email, FAKE_LOGIN_TEXT)

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def send(self, client, method: str, path: str, body=None, query=None):
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
		client = get_test_client(use_cookies=True)
		response = self.send(client, "POST", "/api/method/login", body={"usr": user, "pwd": FAKE_LOGIN_TEXT})
		self.assertEqual(response.status_code, 200, response.data[:300])
		return client

	def pending_request(self) -> str:
		doc = frappe.get_doc(
			doctype=REQUEST,
			reseller_tenant=self.site,
			customer_name="Örnek Müşteri 833",
			contact_email="ornek.musteri.833@example.test",
		).insert(ignore_permissions=True)
		return doc.name

	def test_operator_is_a_system_user(self):
		self.assertEqual(frappe.db.get_value("User", OPERATOR, "user_type"), "System User")

	def test_operator_approves_a_pending_request(self):
		name = self.pending_request()

		response = self.send(
			self.login(OPERATOR), "POST", API + "approve_customer_request", {"request": name}
		)

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"], {"name": name, "status": "Approved"})
		row = frappe.db.get_value(REQUEST, name, ["status", "approved_by"], as_dict=True)
		self.assertEqual(row.status, "Approved")
		self.assertEqual(row.approved_by, OPERATOR)

	def test_an_approved_request_is_not_approved_again(self):
		name = self.pending_request()
		client = self.login(OPERATOR)
		self.assertEqual(
			self.send(client, "POST", API + "approve_customer_request", {"request": name}).status_code, 200
		)

		again = self.send(client, "POST", API + "approve_customer_request", {"request": name})

		self.assertEqual(again.status_code, 417, again.data[:300])

	def test_approving_an_unknown_request_returns_404(self):
		response = self.send(
			self.login(OPERATOR), "POST", API + "approve_customer_request", {"request": "olmayan-istek"}
		)
		self.assertEqual(response.status_code, 404, response.data[:300])

	def test_operator_opens_and_closes_a_link(self):
		client = self.login(OPERATOR)
		created = self.send(
			client,
			"POST",
			REST + LINK,
			{"reseller_tenant": self.site, "customer_tenant": CUSTOMER, "site_status": "Active"},
		)
		self.assertEqual(created.status_code, 200, created.data[:300])
		name = created.json["data"]["name"]

		closed = self.send(client, "DELETE", REST + LINK + "/" + name)

		self.assertIn(closed.status_code, (200, 202), closed.data[:300])
		self.assertFalse(frappe.db.exists(LINK, name))

	def test_one_customer_has_one_reseller(self):
		frappe.get_doc(doctype=LINK, reseller_tenant=self.site, customer_tenant=CUSTOMER).insert(
			ignore_permissions=True
		)
		duplicate = frappe.get_doc(
			doctype=LINK, reseller_tenant="baska-bayi.example.test", customer_tenant=CUSTOMER
		)
		self.assertRaises(frappe.UniqueValidationError, duplicate.insert, ignore_permissions=True)

	def test_operator_cannot_send_a_customer_request(self):
		response = self.send(
			self.login(OPERATOR),
			"POST",
			API + "request_customer",
			{"customer_name": "Örnek", "contact_email": "ornek.833@example.test"},
		)
		self.assertEqual(response.status_code, 403, response.data[:300])

	def test_a_request_needs_a_valid_address_and_a_name(self):
		client = self.login(RESELLER)
		before = frappe.db.count(REQUEST)

		bad_email = self.send(
			client,
			"POST",
			API + "request_customer",
			{"customer_name": "Örnek", "contact_email": "adres-degil"},
		)
		no_name = self.send(
			client,
			"POST",
			API + "request_customer",
			{"customer_name": "  ", "contact_email": "ornek.833@example.test"},
		)

		self.assertEqual(bad_email.status_code, 417, bad_email.data[:300])
		self.assertEqual(no_name.status_code, 417, no_name.data[:300])
		self.assertEqual(frappe.db.count(REQUEST), before)

	def test_a_tenant_admin_is_refused_by_the_reseller_endpoints(self):
		client = self.login(TENANT_ADMIN)
		for method, path, body in (
			("GET", API + "list_customers", None),
			("GET", API + "customer_status", None),
			(
				"POST",
				API + "request_customer",
				{"customer_name": "Örnek", "contact_email": "ornek.833@example.test"},
			),
		):
			query = {"customer_tenant": CUSTOMER} if path.endswith("customer_status") else None
			response = self.send(client, method, path, body, query)
			self.assertEqual(response.status_code, 403, (path, response.data[:300]))
