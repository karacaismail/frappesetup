"""Reseller customers (G-169, G-170). The endpoints are in `platform_core.api.reseller`.

A tenant is its own Frappe site. The reseller tenant of a call is the site that serves it.
A reseller sees only the customers linked to that site. The reseller never reads the business
data of a customer tenant: these functions return the link fields only.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, validate_email_address

LINK = "Reseller Customer Link"
REQUEST = "Reseller Customer Request"
RESELLER_ADMIN = "Reseller Admin"
RESELLER_ASSISTANT = "Reseller Assistant"
PLATFORM_OPERATOR = "Platform Operator"
READERS = (RESELLER_ADMIN, RESELLER_ASSISTANT)
MAX_NAME = 140


def reseller_tenant() -> str:
	return frappe.local.site


def require(roles: tuple[str, ...]) -> None:
	"""Refuses the session user with 403 unless it holds one of the roles."""
	if set(roles).isdisjoint(frappe.get_roles()):
		frappe.throw(_("You are not permitted to do this."), frappe.PermissionError)


def list_customers() -> list[dict]:
	require(READERS)
	rows = frappe.get_all(
		LINK,
		filters={"reseller_tenant": reseller_tenant()},
		fields=["customer_tenant", "customer_name", "site_status"],
		order_by="customer_tenant asc",
		ignore_permissions=True,
	)
	return [
		{
			"customer_tenant": row.customer_tenant,
			"customer_name": row.customer_name,
			"status": row.site_status,
		}
		for row in rows
	]


def customer_status(customer_tenant: str) -> dict:
	require(READERS)
	row = None
	if isinstance(customer_tenant, str) and customer_tenant.strip():
		row = frappe.db.get_value(
			LINK,
			{"reseller_tenant": reseller_tenant(), "customer_tenant": customer_tenant.strip()},
			["customer_tenant", "customer_name", "site_status"],
			as_dict=True,
		)
	if not row:
		# The same answer for a missing customer and for the customer of another reseller.
		frappe.throw(_("You are not permitted to see this customer."), frappe.PermissionError)
	return {
		"customer_tenant": row.customer_tenant,
		"customer_name": row.customer_name,
		"status": row.site_status,
	}


def request_customer(customer_name: str, contact_email: str) -> dict:
	require((RESELLER_ADMIN,))
	name = (customer_name or "").strip() if isinstance(customer_name, str) else ""
	email = (contact_email or "").strip() if isinstance(contact_email, str) else ""
	if not name or len(name) > MAX_NAME:
		frappe.throw(_("Enter the customer name. It can have at most {0} characters.").format(MAX_NAME))
	if not email or not validate_email_address(email):
		frappe.throw(_("Enter a valid contact e-mail address."))
	doc = frappe.get_doc(
		doctype=REQUEST,
		reseller_tenant=reseller_tenant(),
		customer_name=name,
		contact_email=email,
		status="Pending",
		requested_by=frappe.session.user,
	).insert(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


def approve_customer_request(request: str) -> dict:
	require((PLATFORM_OPERATOR,))
	if not isinstance(request, str) or not frappe.db.exists(REQUEST, request):
		frappe.throw(_("The customer request does not exist."), frappe.DoesNotExistError)
	doc = frappe.get_doc(REQUEST, request, for_update=True)
	if doc.status != "Pending":
		frappe.throw(_("Only a pending customer request can be approved."))
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}
