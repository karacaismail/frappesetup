import frappe
from frappe.rate_limiter import rate_limit
from frappe.sessions import delete_session

from press_tr.press_identity.identity import find_identity
from press_tr.press_identity.oidc import claim, client_id, reject, verify


@frappe.whitelist(allow_guest=True, methods=["POST"])
def keycloak_backchannel_logout(logout_token: str | None = None) -> None:
	frappe.form_dict.pop("logout_token", None)
	_revoke_keycloak_sessions(logout_token)


@rate_limit(limit=120, seconds=60)
def _revoke_keycloak_sessions(logout_token: str | None) -> None:
	if not isinstance(logout_token, str) or not logout_token:
		reject()

	from oidc_verify import verify_logout_token

	claims = verify(verify_logout_token, logout_token, client_id=client_id())
	filters = {}
	if "sid" in claims:
		filters["keycloak_sid"] = claim(claims, "sid")
	if "sub" in claims:
		link = find_identity(claim(claims, "iss"), claim(claims, "sub"))
		if not link:
			return
		filters["identity_link"] = link.name
	if not filters:
		reject()

	for name in frappe.get_all("Press Keycloak Session", filters=filters, pluck="name"):
		record = frappe.get_doc("Press Keycloak Session", name)
		sid = record.get_password("press_sid")
		user = frappe.db.get_value("Sessions", {"sid": sid}, "user", order_by=None)
		if user:
			delete_session(sid=sid, user=user, reason="Keycloak logout")
		# A verified logout notification may revoke only its matched internal mappings.
		record.delete(ignore_permissions=True)
