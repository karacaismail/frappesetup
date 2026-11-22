"""Stand-in mobile endpoint for the tests of `platform_core.kimlik.api` (the real ones belong to platform-core-mobil)."""

import frappe


@frappe.whitelist(methods=["POST"])
def v1_whoami() -> dict:
	identity = getattr(frappe.local, "mobile_identity", None) or {}
	return {"user": frappe.session.user, "identity": {k: v for k, v in identity.items() if k != "scope"}}
