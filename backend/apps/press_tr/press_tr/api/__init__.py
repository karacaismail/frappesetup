from functools import wraps

import frappe
from frappe.rate_limiter import rate_limit
from frappe.sessions import delete_session
from packaging.version import Version
from werkzeug.exceptions import ServiceUnavailable

from press_tr.kimlik.identity import find_identity
from press_tr.kimlik.oidc import claim, client_id, reject, verify
from press_tr.kimlik.sessions import SESSION_MAPPING_DOCTYPE, read_press_session_id, session_mapping_pages

MAX_LOGOUT_TOKEN_LENGTH = 8192


def prepare_logout_request(handler):
	@wraps(handler)
	def prepared():
		frappe.flags.press_logout_token = frappe.form_dict.pop("logout_token", None)
		# Frappe 16.50 uses cmd as the counter namespace, even on routes without cmd.
		legacy_limiter = Version(frappe.__version__) < Version("16.56.0")
		command = frappe.form_dict.get("cmd")
		if legacy_limiter:
			frappe.form_dict["cmd"] = "press_tr.api.keycloak_backchannel_logout"
		try:
			return handler()
		finally:
			frappe.flags.pop("press_logout_token", None)
			if legacy_limiter:
				if command is None:
					frappe.form_dict.pop("cmd", None)
				else:
					frappe.form_dict["cmd"] = command

	return prepared


@frappe.whitelist(allow_guest=True, methods=["POST"])
@prepare_logout_request
@rate_limit(limit=1200, seconds=60)
def keycloak_backchannel_logout() -> None:
	_revoke_keycloak_sessions(frappe.flags.pop("press_logout_token", None))


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
		if not isinstance(logout_token, str) or not 1 <= len(logout_token) <= MAX_LOGOUT_TOKEN_LENGTH:
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

	try:
		_revoke_matching_sessions(filters)
	except Exception as error:
		# The batch contains decrypted session credentials. Keep its locals out of error logs.
		frappe.logger("press_tr").warning("Keycloak session revocation failed: %s", type(error).__name__)
		raise ServiceUnavailable() from None


def _revoke_matching_sessions(filters: dict) -> None:
	sessions = frappe.qb.DocType("Sessions")
	for names in session_mapping_pages(filters):
		mappings = {name: read_press_session_id(name) for name in names}
		users = dict(
			frappe.qb.from_(sessions)
			.select(sessions.sid, sessions.user)
			.where(sessions.sid.isin(list(mappings.values())))
			.run()
		)
		for name, sid in mappings.items():
			if user := users.pop(sid, None):
				delete_session(sid=sid, user=user, reason="Keycloak logout")
			# A verified logout notification may revoke only its matched internal mappings.
			frappe.delete_doc(SESSION_MAPPING_DOCTYPE, name, ignore_permissions=True)
