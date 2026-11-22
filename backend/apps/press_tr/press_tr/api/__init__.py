from contextlib import contextmanager

import frappe
from frappe.rate_limiter import rate_limit
from frappe.sessions import delete_session
from packaging.version import Version
from werkzeug.exceptions import ServiceUnavailable

from press_tr.kimlik.identity import find_identity
from press_tr.kimlik.oidc import claim, client_id, reject, verify
from press_tr.kimlik.sessions import SESSION_MAPPING_DOCTYPE, read_press_session_id, session_mapping_pages

MAX_LOGOUT_TOKEN_LENGTH = 8192


@contextmanager
def rate_limit_namespace(command: str):
	# Frappe 16.56 uses the function name. Earlier versions use form_dict.cmd.
	if Version(frappe.__version__) >= Version("16.56.0"):
		yield
		return

	original = frappe.form_dict.get("cmd")
	frappe.form_dict["cmd"] = command
	try:
		yield
	finally:
		if original is None:
			frappe.form_dict.pop("cmd", None)
		else:
			frappe.form_dict["cmd"] = original


@frappe.whitelist(allow_guest=True, methods=["POST"])
def keycloak_backchannel_logout() -> None:
	# The contract exempts verified notifications from rate limiting.
	_revoke_keycloak_sessions(frappe.form_dict.pop("logout_token", None))


@rate_limit(limit=120, seconds=60)
def _count_rejected_logout() -> None:
	pass


def count_rejected_logout() -> None:
	with rate_limit_namespace("press_tr.rejected_logout"):
		_count_rejected_logout()


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
