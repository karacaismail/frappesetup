"""Guest and foreign data tests of the reseller endpoints (G-169, G-170, AJA-899).

Written before any code change (D-2). The security audit of `backend/dev/security/endpoints.py`
asks two named tests for each endpoint of `platform_core.api.reseller`. These tests send real
requests through the WSGI application of Frappe (D-6) and run with `backend/dev/bin/test platform_core`.

A tenant is its own Frappe site. The other reseller is the made-up tenant `OTHER_RESELLER`.
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
FAKE_LOGIN_TEXT = "Sahte-Parola-898-bayi!"
RESELLER = "pr.bayi.898@example.test"
OTHER_RESELLER = "baska-bayi-898.example.test"
OWN_CUSTOMER = "kendi-musteri-898.example.test"
OTHER_CUSTOMER = "baska-musteri-898.example.test"
NEW_REQUEST = {"customer_name": "Örnek Müşteri 898", "contact_email": "ornek.898@example.test"}


@unittest.skipIf(frappe is None, "Frappe is not installed: the HTTP tests run with backend/dev/bin/test")
class TestResellerEndpointSecurity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.site = frappe.local.site
		cls.clean()
		doc = frappe.get_doc(
			doctype="User",
			email=RESELLER,
			first_name="pr.bayi.898",
			send_welcome_email=0,
			role_profiles=[{"role_profile": "Reseller Admin"}],
		)
		doc.insert(ignore_permissions=True)
		update_password(RESELLER, FAKE_LOGIN_TEXT)
		for reseller, customer in ((cls.site, OWN_CUSTOMER), (OTHER_RESELLER, OTHER_CUSTOMER)):
			frappe.get_doc(
				doctype=LINK,
				reseller_tenant=reseller,
				customer_tenant=customer,
				customer_name=customer,
				site_status="Active",
			).insert(ignore_permissions=True)
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
		if frappe.db.exists("User", RESELLER):
			frappe.delete_doc("User", RESELLER, force=True, ignore_permissions=True)

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

	def guest(self):
		return get_test_client(use_cookies=True)

	def login(self):
		client = get_test_client(use_cookies=True)
		response = self.send(
			client, "POST", "/api/method/login", body={"usr": RESELLER, "pwd": FAKE_LOGIN_TEXT}
		)
		self.assertEqual(response.status_code, 200, response.data[:300])
		return client

	def foreign_request(self) -> str:
		doc = frappe.get_doc(
			doctype=REQUEST,
			reseller_tenant=OTHER_RESELLER,
			customer_name="Başka Bayi Müşterisi 898",
			contact_email="baska.musteri.898@example.test",
		).insert(ignore_permissions=True)
		return doc.name

	def assert_denied(self, response):
		self.assertEqual(response.status_code, 403, response.data[:300])
		self.assertNotIn(OWN_CUSTOMER.encode(), response.data)
		self.assertNotIn(OTHER_CUSTOMER.encode(), response.data)

	def test_list_customers_guest_denied(self):
		self.assert_denied(self.send(self.guest(), "GET", API + "list_customers"))

	def test_list_customers_foreign_data_denied(self):
		response = self.send(self.login(), "GET", API + "list_customers")

		self.assertEqual(response.status_code, 200, response.data[:300])
		listed = [row["customer_tenant"] for row in response.json["message"]["items"]]
		self.assertEqual(listed, [OWN_CUSTOMER])
		self.assertNotIn(OTHER_CUSTOMER.encode(), response.data)

	def test_customer_status_guest_denied(self):
		response = self.send(
			self.guest(), "GET", API + "customer_status", query={"customer_tenant": OWN_CUSTOMER}
		)
		self.assert_denied(response)

	def test_customer_status_foreign_data_denied(self):
		response = self.send(
			self.login(), "GET", API + "customer_status", query={"customer_tenant": OTHER_CUSTOMER}
		)
		self.assert_denied(response)

	def test_request_customer_guest_denied(self):
		before = frappe.db.count(REQUEST)

		self.assert_denied(self.send(self.guest(), "POST", API + "request_customer", NEW_REQUEST))

		self.assertEqual(frappe.db.count(REQUEST), before)

	def test_request_customer_foreign_data_denied(self):
		# The reseller names the other reseller. The endpoint must use the serving site only.
		body = {**NEW_REQUEST, "reseller_tenant": OTHER_RESELLER, "customer_tenant": OTHER_CUSTOMER}
		foreign_before = frappe.db.count(REQUEST, {"reseller_tenant": OTHER_RESELLER})

		response = self.send(self.login(), "POST", API + "request_customer", body)

		self.assertEqual(response.status_code, 200, response.data[:300])
		name = response.json["message"]["name"]
		self.assertEqual(frappe.db.get_value(REQUEST, name, "reseller_tenant"), self.site)
		self.assertEqual(frappe.db.count(REQUEST, {"reseller_tenant": OTHER_RESELLER}), foreign_before)

	def test_approve_customer_request_guest_denied(self):
		name = self.foreign_request()

		response = self.send(self.guest(), "POST", API + "approve_customer_request", {"request": name})

		self.assert_denied(response)
		self.assertEqual(frappe.db.get_value(REQUEST, name, "status"), "Pending")

	def test_approve_customer_request_foreign_data_denied(self):
		name = self.foreign_request()

		response = self.send(self.login(), "POST", API + "approve_customer_request", {"request": name})

		self.assert_denied(response)
		self.assertEqual(frappe.db.get_value(REQUEST, name, "status"), "Pending")

	def test_list_customers_pages_stay_scoped_to_the_reseller(self):
		client = self.login()
		first = self.send(client, "GET", API + "list_customers", query={"page_size": 1, "offset": 0})
		self.assertEqual(first.status_code, 200, first.data[:300])
		self.assertEqual(
			first.json["message"],
			{
				"items": [
					{"customer_tenant": OWN_CUSTOMER, "customer_name": OWN_CUSTOMER, "status": "Active"}
				],
				"has_more": False,
				"offset": 0,
				"page_size": 1,
			},
		)
		last = self.send(client, "GET", API + "list_customers", query={"page_size": 1, "offset": 1})
		self.assertEqual(last.status_code, 200, last.data[:300])
		self.assertEqual(last.json["message"]["items"], [])
		self.assertFalse(last.json["message"]["has_more"])
		self.assertNotIn(OTHER_CUSTOMER.encode(), first.data + last.data)

	def test_list_customers_clamps_large_pages_and_reports_the_next_page(self):
		names = []
		try:
			for index in range(201):
				doc = frappe.get_doc(
					doctype=LINK,
					reseller_tenant=self.site,
					customer_tenant=f"page-{index:03d}.example.test",
					customer_name="Synthetic page customer",
					site_status="Active",
				).insert()
				names.append(doc.name)
			client = self.login()
			first = self.send(client, "GET", API + "list_customers", query={"page_size": 999999})
			self.assertEqual(first.status_code, 200, first.data[:300])
			page = first.json["message"]
			self.assertEqual(page["page_size"], 100)
			self.assertEqual(len(page["items"]), 100)
			self.assertTrue(page["has_more"])
			seen = [item["customer_tenant"] for item in page["items"]]
			for offset, expected_size, has_more in ((100, 100, True), (200, 2, False)):
				response = self.send(
					client, "GET", API + "list_customers", query={"page_size": 100, "offset": offset}
				)
				self.assertEqual(response.status_code, 200, response.data[:300])
				page = response.json["message"]
				self.assertEqual(len(page["items"]), expected_size)
				self.assertEqual(page["has_more"], has_more)
				seen.extend(item["customer_tenant"] for item in page["items"])
			self.assertEqual(len(set(seen)), 202)
			self.assertEqual(seen, sorted(seen))
			self.assertNotIn(OTHER_CUSTOMER, seen)
		finally:
			frappe.set_user("Administrator")
			frappe.db.delete(LINK, {"name": ["in", names]})
			frappe.db.commit()  # nosemgrep: frappe-request-commit

	def test_list_customers_rejects_invalid_pagination(self):
		client = self.login()
		for query in (
			{"page_size": 0},
			{"page_size": -1},
			{"offset": -1},
			{"offset": "x"},
			{"page_size": "1.5"},
			{"offset": str(2**64)},
		):
			with self.subTest(query=query):
				response = self.send(client, "GET", API + "list_customers", query=query)
				self.assertEqual(response.status_code, 417, response.data[:300])
