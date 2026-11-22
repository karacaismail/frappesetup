"""HTTP entry point for shell bootstrap."""

import frappe

from platform_core.kabuk.bootstrap import get_bootstrap as read_bootstrap


@frappe.whitelist(methods=["GET"])
def get_bootstrap() -> dict | None:
	"""Read the current user's installed applications and permitted navigation."""
	return read_bootstrap()
