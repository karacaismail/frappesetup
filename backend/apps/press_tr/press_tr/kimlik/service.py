import frappe

from press_tr.kimlik.oidc import client_id, reject, verify
from press_tr.kimlik.oidc import issuer as configured_issuer

SERVICE_PARAMETERS = {
	"press_tr.api.identity.list_identities": {"cursor", "limit"},
	"press_tr.api.identity.anonymize_user": {"issuer", "subject"},
	"press_tr.api.identity.ensure_team": {
		"issuer",
		"subject",
		"email",
		"email_verified",
		"organization_id",
		"organization_name",
	},
	"press_tr.api.identity.remove_team_member": {"issuer", "subject", "organization_id", "all_organizations"},
}


def authorize_identity_sync() -> None:
	method = frappe.request.path.rstrip("/").removeprefix("/api/method/")
	if method not in SERVICE_PARAMETERS:
		return
	if frappe.request.method != "POST":
		return
	session = getattr(frappe.local, "session_obj", None)
	cookie_sid = frappe.request.cookies.get("sid")
	has_user_session = bool(cookie_sid and session and session.sid == cookie_sid and session.user != "Guest")
	if frappe.form_dict.keys() - SERVICE_PARAMETERS[method] or has_user_session:
		reject()

	scheme, _, token = frappe.get_request_header("Authorization", "").partition(" ")
	if scheme.lower() != "bearer" or not token or any(character.isspace() for character in token):
		reject()

	from oidc_verify import verify_access_token

	verify(verify_access_token, token, audience=client_id(), allowed_azp={"identity-sync"})
	service_user = frappe.conf.press_identity_sync_user
	if not service_user or service_user in {"Guest", "Administrator"}:
		reject()
	enabled, user_type = frappe.db.get_value("User", service_user, ["enabled", "user_type"]) or (False, None)
	if not enabled or user_type != "Website User":
		reject()

	form_dict = frappe.form_dict.copy()
	frappe.set_user(service_user)
	frappe.local.form_dict.update(form_dict)
	frappe.local.flags.press_identity_sync = True


def require_service(issuer: str) -> None:
	if not frappe.local.flags.press_identity_sync or issuer != configured_issuer():
		reject()
