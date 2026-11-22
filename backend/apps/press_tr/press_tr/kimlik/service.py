import frappe

from press_tr.kimlik.oidc import issuer as configured_issuer
from press_tr.kimlik.oidc import reject, verify

SERVICE_PARAMETERS = {
	"press_tr.api.identity.ensure_team": {
		"issuer",
		"subject",
		"email",
		"organization_id",
		"organization_name",
	},
	"press_tr.api.identity.remove_team_member": {"issuer", "subject", "organization_id"},
}


def authorize_identity_sync() -> None:
	method = frappe.request.path.rstrip("/").removeprefix("/api/method/")
	if method not in SERVICE_PARAMETERS:
		return
	if frappe.request.method != "POST":
		return
	if frappe.form_dict.keys() - SERVICE_PARAMETERS[method] or "sid" in frappe.request.cookies:
		reject()

	scheme, _, token = frappe.get_request_header("Authorization", "").partition(" ")
	if scheme.lower() != "bearer" or not token or any(character.isspace() for character in token):
		reject()

	from oidc_verify import verify_access_token

	verify(verify_access_token, token, audience="press", allowed_azp={"identity-sync"})
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
