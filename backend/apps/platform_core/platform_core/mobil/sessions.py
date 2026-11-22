"""Persist local Keycloak session denial and dispatch remote closure after commit."""

import re
import time

import frappe

from .identity_sync_client import send_session_revocations
from .metadata import insert_metadata
from .protocol import MobileError, content_digest

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


def pending_session_closures(session_ids):
	sessions_by_key = {_session_key(sid): sid for sid in session_ids if valid_keycloak_id(sid)}
	if not sessions_by_key:
		return set()
	pending_keys = frappe.db.get_values(
		REVOKED_SESSION,
		{"name": ["in", list(sessions_by_key)], "delivery_pending": 1},
		"name",
		pluck=True,
	)
	return {sessions_by_key[key] for key in pending_keys}


def revoke_after_commit(sessions, *, remote=True):
	targets = sorted({(sid, subject or "") for sid, subject in sessions if valid_keycloak_id(sid)})
	if not targets:
		return
	keys = {sid: _session_key(sid) for sid, _unused in targets}
	rows = frappe.db.get_values(
		REVOKED_SESSION,
		{"name": ["in", list(keys.values())]},
		["name", "delivery_pending", "last_delivery_attempt_at"],
		as_dict=True,
		for_update=True,
	)
	persisted = {row.name: row for row in rows}
	pending = []
	missing_subject = False
	retry_keys = []
	cancel_keys = []
	now = int(time.time())
	for sid, subject in targets:
		deliver = remote and valid_keycloak_id(subject)
		key = keys[sid]
		row = persisted.get(key)
		if remote and not deliver and (row is None or row.delivery_pending):
			missing_subject = True
		if row is None:
			persisted[key] = insert_metadata(
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
				cancel_keys.append(key)
			elif deliver and now - int(row.last_delivery_attempt_at or 0) >= DELIVERY_RETRY_SECONDS:
				retry_keys.append(key)
				row.last_delivery_attempt_at = str(now)
				pending.append((sid, subject))
	if cancel_keys:
		frappe.db.set_value(REVOKED_SESSION, {"name": ["in", cancel_keys]}, "delivery_pending", 0)
	if retry_keys:
		frappe.db.set_value(
			REVOKED_SESSION, {"name": ["in", retry_keys]}, "last_delivery_attempt_at", str(now)
		)

	if missing_subject:
		frappe.logger("mobile_sessions").warning(
			"Mobile session closure is pending because the Keycloak subject is unavailable."
		)
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
	retryable = set(send_session_revocations(sessions))
	completed = [_session_key(sid) for sid, subject in sessions if (sid, subject) not in retryable]
	if not completed:
		return
	# In the requestless path, the parent commit may still have callbacks to run.
	# The separate acknowledgment transaction must not drain or clear them.
	original_callbacks = frappe.db.after_commit.cut(0)
	try:
		frappe.db.set_value(REVOKED_SESSION, {"name": ["in", completed]}, "delivery_pending", 0)
		frappe.db.commit()  # nosemgrep: acknowledge after the revocation transaction committed
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
		# The pending marker is already durable. Retry the same installation if acknowledgement fails.
		frappe.db.rollback()
		frappe.logger("mobile_sessions").warning("A mobile session closure could not be acknowledged.")
	finally:
		for callback in original_callbacks:
			frappe.db.after_commit.add(callback)
