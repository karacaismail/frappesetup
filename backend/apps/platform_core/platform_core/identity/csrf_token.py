"""The CSRF token of the current session for the separate frontend (`platform_core.api.auth.get_csrf_token`)."""

import hashlib

import frappe
import frappe.sessions

# The lock only guards token creation, which is one Redis and one database write.
LOCK_TIMEOUT_SECONDS = 10
LOCK_WAIT_SECONDS = 5


def _lock_name(sid: str) -> str:
	# The session id is a secret, so the Redis key carries only its digest.
	return frappe.cache.make_key(f"platform_core:csrf_token:{hashlib.sha256(sid.encode()).hexdigest()}")


def _stored_token(sid: str) -> str | None:
	"""Reads the token from the shared session record, not from the copy this request loaded."""
	frappe.local.cache.get(frappe.cache.make_key("session"), {}).pop(sid, None)
	record = frappe.cache.hget("session", sid)
	return ((record or {}).get("data") or {}).get("csrf_token")


def session_csrf_token() -> str:
	"""Returns the session token. Only one request per session creates the first token.

	Two tabs share one session. If both ask before a token exists, both would create one and the last
	write would win (frappe/sessions.py:202-212). The request that holds the lock creates and stores the
	token. A request that waited reads that token from the shared session record. Frappe writes the
	record to the cache after the database commit (frappe/sessions.py:452).
	"""
	session = frappe.local.session
	if session.data.csrf_token:
		return session.data.csrf_token
	lock = frappe.cache.lock(
		_lock_name(session.sid), timeout=LOCK_TIMEOUT_SECONDS, blocking_timeout=LOCK_WAIT_SECONDS
	)
	with lock:
		if token := _stored_token(session.sid):
			session.data.csrf_token = token
			return token
		return frappe.sessions.get_csrf_token()
