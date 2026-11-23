"""AtonotA Login action decision endpoints (G-161, G-166).

The Frappe link is in `platform_core.identity.atonota.decision_api`. The rules are in the
`atonota_login` package. Contract: `backend/contracts/platform_core-identity.openapi.yaml`, tag `atonota-login`.
"""

from typing import Any

import frappe

from platform_core.identity.atonota import decision_api


@frappe.whitelist(methods=["POST"])
def evaluate(action: Any = None) -> dict:
	"""Says whether the signed-in user may take one action now. The server collects the evidence.

	`action` has no narrow type on purpose: the link checks it and answers `InvalidInput` (contract: 400).
	"""
	return decision_api.evaluate(action)


@frappe.whitelist(methods=["POST"])
def open_paid_plan() -> dict:
	"""Opens a paid AtonotA Login plan. Closed until the price decision (G-166)."""
	return decision_api.open_paid_plan()
