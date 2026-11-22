"""Persist local Keycloak session denial and dispatch remote closure after commit."""

import re
import time

import frappe

from .identity_sync_client import send_session_revocations
from .protocol import MobileError, content_digest
from .store import _insert

DELIVERY_RETRY_SECONDS = 60
REVOKED_SESSION = "Mobile Revoked Session"
KEYCLOAK_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


def valid_keycloak_id(value):
	return isinstance(value, str) and KEYCLOAK_ID_PATTERN.fullmatch(value) is not None


def _session_key(sid):
	return content_digest(["mobile-session-v1", sid])


def is_session_revoked(sid, *, for_update=False):
	return bool(frappe.db.get_value(REVOKED_SESSION, _session_key(sid), "name", for_update=for_update))


def require_active_session(sid, *, for_update=False):
	if is_session_revoked(sid, for_update=for_update):
		raise MobileError("mobile_session_revoked", 401)


def is_session_closure_pending(sid):
	if not valid_keycloak_id(sid):
		return False
	return bool(frappe.db.get_value(REVOKED_SESSION, _session_key(sid), "delivery_pending"))


def revoke_after_commit(sessions, *, remote=True):
	pending = []
	now = int(time.time())
	targets = {(sid, subject or "") for sid, subject in sessions if valid_keycloak_id(sid)}
	for sid, subject in sorted(targets):
		deliver = remote and valid_keycloak_id(subject)
		key = _session_key(sid)
		row = frappe.db.get_value(
			REVOKED_SESSION,
			key,
			["delivery_pending", "last_delivery_attempt_at"],
			as_dict=True,
			for_update=True,
		)
		if row is None:
			_insert(
				REVOKED_SESSION,
				session_key=key,
				delivery_pending=int(remote),
				last_delivery_attempt_at=str(now) if deliver else None,
				ignore_duplicate=True,
			)
			if deliver:
				pending.append((sid, subject))
		elif row.delivery_pending:
			if not remote:
				frappe.db.set_value(REVOKED_SESSION, key, "delivery_pending", 0)
			elif deliver and now - int(row.last_delivery_attempt_at or 0) >= DELIVERY_RETRY_SECONDS:
				frappe.db.set_value(REVOKED_SESSION, key, "last_delivery_attempt_at", str(now))
				pending.append((sid, subject))

	if pending:
		# A failed transaction or its retry cannot send the remote request.
		request = getattr(frappe.local, "request", None)
		queue = getattr(request, "after_response", None)
		sessions = tuple(pending)
		if queue is None:
			frappe.db.after_commit.add(lambda: _deliver_committed(sessions))
		else:
			frappe.db.after_commit.add(lambda: queue.add(lambda: _deliver_committed(sessions)))


def _deliver_committed(sessions):
	try:
		failed = set(send_session_revocations(sessions))
		confirmed = [_session_key(sid) for sid, subject in sessions if (sid, subject) not in failed]
		if confirmed:
			frappe.db.set_value(REVOKED_SESSION, {"name": ["in", confirmed]}, "delivery_pending", 0)
			frappe.db.commit()  # nosemgrep: acknowledge after the revocation transaction committed
	except Exception:
		# The pending marker is already durable. Retry the same installation if acknowledgement fails.
		frappe.logger("mobile_sessions").warning("A mobile session closure could not be acknowledged.")
