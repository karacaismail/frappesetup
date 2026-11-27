"""Checks both reseller roles share (G-169, G-170, AJA-831). Written before the code (D-2).

The reseller sees only the customers linked to its own tenant. A request about the customer of
another reseller is refused. The reseller never reads the business data of a customer tenant.
For example a leave record request is refused. Only a "Platform Operator" opens and closes a link.
"""

from platform_core.access.tests import panel_roles
from platform_core.access.tests.panel_roles import (
	LINK_DOCTYPE,
	OTHER_CUSTOMER,
	OWN_CUSTOMERS,
	REQUEST_DOCTYPE,
	RESELLER_API,
	UNKNOWN_CUSTOMER,
	frappe,
)

# Business data of a tenant. A reseller reads none of it.
BUSINESS_DOCTYPES = ("Employee", "Leave Application")


class ResellerChecks:
	"""Mixed into the HTTP test class of each reseller role."""

	MAKE_LINKS = True

	def test_reseller_lists_only_its_linked_customers(self):
		response = self.call(self.login(), "GET", RESELLER_API + "list_customers")

		self.assertEqual(response.status_code, 200, response.data[:300])
		listed = {row["customer_tenant"] for row in response.json["message"]["items"]}
		self.assertEqual(listed, set(OWN_CUSTOMERS))
		self.assertNotIn(OTHER_CUSTOMER, listed)

	def test_reseller_reads_the_status_of_its_own_customer(self):
		customer = OWN_CUSTOMERS[0]
		response = self.call(self.login(), "GET", RESELLER_API + "customer_status", customer_tenant=customer)

		self.assertEqual(response.status_code, 200, response.data[:300])
		self.assertEqual(response.json["message"]["customer_tenant"], customer)
		self.assertIn("status", response.json["message"])

	def test_reseller_is_refused_for_the_customer_of_another_reseller(self):
		client = self.login()

		other = self.assert_denied(
			client, "GET", RESELLER_API + "customer_status", customer_tenant=OTHER_CUSTOMER
		)
		unknown = self.assert_denied(
			client, "GET", RESELLER_API + "customer_status", customer_tenant=UNKNOWN_CUSTOMER
		)

		# The answer does not show whether the other customer exists.
		self.assertNotIn(OTHER_CUSTOMER.encode(), other.data)
		self.assertEqual(other.status_code, unknown.status_code)

	def test_reseller_cannot_read_business_data_of_a_customer(self):
		"""For example the leave records of a customer tenant. The type may not exist on the site."""
		client = self.login()
		for doctype in BUSINESS_DOCTYPES:
			response = self.send(client, "GET", panel_roles.REST + doctype)
			self.assertIn(response.status_code, (403, 404), (doctype, response.data[:300]))
		leave = self.send(
			client, "GET", panel_roles.REST + "Leave Application", query={"customer_tenant": OWN_CUSTOMERS[0]}
		)
		self.assertIn(leave.status_code, (403, 404), leave.data[:300])

	def test_reseller_cannot_open_change_or_close_a_link(self):
		client = self.login()
		link = frappe.get_all(LINK_DOCTYPE, filters={"customer_tenant": OWN_CUSTOMERS[0]}, pluck="name")[0]

		self.assert_rest_denied(
			client,
			"POST",
			LINK_DOCTYPE,
			body={"reseller_tenant": self.site, "customer_tenant": OTHER_CUSTOMER},
		)
		self.assert_rest_denied(client, "PUT", LINK_DOCTYPE, link, body={"customer_tenant": OTHER_CUSTOMER})
		self.assert_rest_denied(client, "DELETE", LINK_DOCTYPE, link)

		self.assertEqual(frappe.db.get_value(LINK_DOCTYPE, link, "customer_tenant"), OWN_CUSTOMERS[0])
		self.assertFalse(
			frappe.db.exists(LINK_DOCTYPE, {"reseller_tenant": self.site, "customer_tenant": OTHER_CUSTOMER})
		)

	def test_reseller_is_refused_by_the_g62_endpoints(self):
		client = self.login()
		self.assert_denied(client, "GET", panel_roles.ACCESS_API + "list_role_permissions", doctype="ToDo")
		self.assert_rest_denied(
			client, "POST", "User", body={"email": "pr.bayi.yeni@example.test", "first_name": "pr"}
		)

	def count_requests(self) -> int:
		return frappe.db.count(REQUEST_DOCTYPE)
