"""Reseller endpoints (G-169, G-170). The business rule is in `platform_core.reseller.customers`.

Contract: `backend/contracts/platform_core-reseller.openapi.yaml`.
"""

import frappe

from platform_core.reseller import customers


@frappe.whitelist(methods=["GET"])
def list_customers(offset: int | str = 0, page_size: int | str = customers.DEFAULT_PAGE_SIZE) -> dict:
	"""Returns the customers linked to the reseller tenant. “Reseller Admin” and “Reseller Assistant”."""
	return customers.list_customers(offset=offset, page_size=page_size)


@frappe.whitelist(methods=["GET"])
def customer_status(customer_tenant: str = "") -> dict:
	"""Returns the site status of one linked customer. Any other customer gets 403."""
	return customers.customer_status(customer_tenant)


@frappe.whitelist(methods=["POST"])
def request_customer(customer_name: str = "", contact_email: str = "") -> dict:
	"""Opens a request for a new customer tenant. “Reseller Admin” only."""
	return customers.request_customer(customer_name, contact_email)


@frappe.whitelist(methods=["POST"])
def approve_customer_request(request: str = "") -> dict:
	"""Approves one pending customer request. “Platform Operator” only."""
	return customers.approve_customer_request(request)
