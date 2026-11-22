"""Persist local Keycloak session denial and dispatch remote closure after commit."""

import re

import frappe

from .identity_sync_client import send_session_revocations
from .protocol import MobileError, content_digest
from .store import _insert

REVOKED_SESSION = "Mobile Revoked Session"
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9._~-]{1,140}")


def valid_session_id(value):
	return isinstance(value, str) and SESSION_ID_PATTERN.fullmatch(value) is not None


def _session_key(sid):
	return content_digest(["mobile-session-v1", sid])


def is_session_revoked(sid, *, for_update=False):
	return bool(frappe.db.get_value(REVOKED_SESSION, _session_key(sid), "name", for_update=for_update))


def require_active_session(sid, *, for_update=False):
	if is_session_revoked(sid, for_update=for_update):
		raise MobileError("mobile_session_revoked", 401)


def is_session_closure_pending(sid):
	if not valid_session_id(sid):
		return False
	return bool(frappe.db.get_value(REVOKED_SESSION, _session_key(sid), "delivery_pending"))


def revoke_after_commit(session_ids):
	pending = []
	for sid in sorted({sid for sid in session_ids if valid_session_id(sid)}):
		key = _session_key(sid)
		row = frappe.db.get_value(
			REVOKED_SESSION,
			key,
			["name", "delivery_pending"],
			as_dict=True,
			for_update=True,
		)
		if row is None:
			_insert(REVOKED_SESSION, session_key=key, delivery_pending=1, ignore_duplicate=True)
		if row is None or row.delivery_pending:
			pending.append(sid)

	if pending:
		# A failed transaction or its retry cannot send the remote request.
		frappe.db.after_commit.add(lambda: _deliver_committed(tuple(pending)))


def _deliver_committed(session_ids):
	try:
		failed = set(send_session_revocations(session_ids))
		confirmed = [_session_key(sid) for sid in session_ids if sid not in failed]
		if confirmed:
			frappe.db.set_value(REVOKED_SESSION, {"name": ["in", confirmed]}, "delivery_pending", 0)
			frappe.db.commit()  # nosemgrep: acknowledge after the revocation transaction committed
	except Exception:
		# The pending marker is already durable. Retry the same installation if acknowledgement fails.
		frappe.db.rollback()
		frappe.logger("mobile_sessions").warning("A mobile session closure could not be acknowledged.")
