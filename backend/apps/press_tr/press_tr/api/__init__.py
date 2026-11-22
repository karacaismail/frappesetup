import frappe
from frappe.rate_limiter import rate_limit
from frappe.sessions import delete_session
from packaging.version import Version

from press_tr.kimlik.identity import find_identity
from press_tr.kimlik.oidc import claim, client_id, reject, verify


@frappe.whitelist(allow_guest=True, methods=["POST"])
def keycloak_backchannel_logout(logout_token: str | None = None) -> None:
	frappe.form_dict.pop("logout_token", None)
	_revoke_keycloak_sessions(logout_token)


@rate_limit(limit=120, seconds=60)
def _count_rejected_logout() -> None:
	pass


def count_rejected_logout() -> None:
	# Frappe 16.56 derives the namespace from the function, regardless of the API version.
	if Version(frappe.__version__) >= Version("16.56.0"):
		_count_rejected_logout()
		return

	# The pinned Press bench uses Frappe 16.50, where v2 does not populate cmd.
	command = frappe.form_dict.get("cmd")
	frappe.form_dict.cmd = "press_tr.rejected_logout"
	try:
		_count_rejected_logout()
	finally:
		if command is None:
			frappe.form_dict.pop("cmd", None)
		else:
			frappe.form_dict.cmd = command


def _revoke_keycloak_sessions(logout_token: str | None) -> None:
	from oidc_verify import verify_logout_token

	try:
		if not isinstance(logout_token, str) or not logout_token:
			reject()
		claims = verify(verify_logout_token, logout_token, client_id=client_id())
	except frappe.PermissionError:
		count_rejected_logout()
		raise
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
