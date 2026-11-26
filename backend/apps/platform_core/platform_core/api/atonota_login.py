"""`atonota_login` endpoints: action decisions (G-161, G-166) and the verification inbox (G-164).

The Frappe links are in `platform_core.identity.atonota.decision_api` and `.verification_api`. The rules are in the
`atonota_login` package. Contract: `backend/contracts/platform_core-identity.openapi.yaml`, tag `atonota-login`.
"""

from typing import Any

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.identity.atonota import decision_api, verification_api
from platform_core.identity.safe_errors import safe_errors


@frappe.whitelist(methods=["POST"])
def evaluate(action: Any = None) -> dict:
	"""Says whether the signed-in user may take one action now. The server collects the evidence.

	`action` has no narrow type on purpose: the link checks it and answers `InvalidInput` (contract: 400).
	"""
	return decision_api.evaluate(action)


@frappe.whitelist(methods=["POST"])
def open_paid_plan() -> dict:
	"""Opens a paid `atonota_login` plan. Closed until the price decision (G-166)."""
	return decision_api.open_paid_plan()


# The provider carries no session. The signature over the raw body authorizes the notice.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=verification_api.RATE_LIMIT, seconds=verification_api.RATE_WINDOW_SECONDS)
@safe_errors
def verification_notice() -> dict:
	"""Receives one result notice of the external verification provider (G-164).

	The body is read raw from `frappe.request`; form fields are not used. Processing runs in the queue.
	"""
	return verification_api.receive_notice()
