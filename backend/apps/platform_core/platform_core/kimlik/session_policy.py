"""Session lifetime rules (PROJE-KAYDI.md O-25).

- The Frappe cookie session ends after 1 hour without activity, for employees and customers.
  Frappe reads the idle limit from System Settings `session_expiry` (frappe/sessions.py:523) and checks
  it on every resume, in the cache (frappe/sessions.py:373) and in the database fallback
  (frappe/sessions.py:499). `apply` writes the limit on install and on every migrate.
- Idle time is measured from real user activity (review finding Ö2). Frappe renews a session on every
  request, background polling included. `before_request` keeps its own activity key per session and per
  user in Redis. Background requests do not renew it. A session without a live key ends with 401.
- An employee (System User) who was idle for the limit authenticates again at Keycloak. The open
  Keycloak cookie must not skip this step: the login restarts with `prompt=login`, and the forced attempt
  accepts only an `auth_time` from that attempt. Customers keep the Keycloak idle window of 7 days.
"""

import time

import frappe

IDLE_TIMEOUT = "01:00:00"
IDLE_SECONDS = 3600
EMPLOYEE_USER_TYPE = "System User"
ACTIVITY_PREFIX = "kimlik_activity"
AUTH_TIME_LEEWAY = 30
BACKGROUND_HEADER = "X-Platform-Background"
# Polling and realtime helpers of the desk. They keep a tab alive but are not user activity.
BACKGROUND_METHOD_PREFIXES = (
	"frappe.realtime.",
	"frappe.desk.notifications.",
	"frappe.auth.get_logged_user",
	"frappe.sessions.get",
)


def apply() -> None:
	"""Writes the idle limit into System Settings. Called by `after_install` and `after_migrate`."""
	if frappe.db.get_single_value("System Settings", "session_expiry") != IDLE_TIMEOUT:
		# V-1 exception: a single field of a single DocType, no validation side effects are wanted here.
		frappe.db.set_single_value("System Settings", "session_expiry", IDLE_TIMEOUT)
		frappe.clear_cache()


def _session_key(sid: str) -> str:
	return f"{ACTIVITY_PREFIX}:sid:{sid}"


def _user_key(user: str) -> str:
	return f"{ACTIVITY_PREFIX}:user:{user}"


def mark_activity(sid: str | None, user: str) -> None:
	"""Records real user activity. Each key lives for the idle limit and is renewed by real requests."""
	if sid and sid != "Guest":
		frappe.cache.set_value(_session_key(sid), int(time.time()), expires_in_sec=IDLE_SECONDS)
	frappe.cache.set_value(_user_key(user), int(time.time()), expires_in_sec=IDLE_SECONDS)


def recently_active(user: str) -> bool:
	return frappe.cache.get_value(_user_key(user), expires=True, use_local_cache=False) is not None


def on_session_creation(login_manager=None) -> None:
	"""`on_session_creation` hook (frappe/auth.py:246): a new session counts as activity."""
	mark_activity(frappe.session.sid, frappe.session.user)


def is_background_request(request) -> bool:
	"""Requests that must not renew the idle time (O-25: background sync does not extend sessions)."""
	if request.headers.get(BACKGROUND_HEADER) == "1":
		return True
	path = request.path or ""
	method = path.split("/api/method/", 1)[1] if "/api/method/" in path else (request.form.get("cmd") or "")
	return method.startswith(BACKGROUND_METHOD_PREFIXES)


def before_request() -> None:
	"""Ends a cookie session whose last real activity is older than the idle limit.

	Frappe renews `last_updated` on every request, background polling included (frappe/sessions.py:420).
	This hook measures real activity instead. Token requests (service and mobile) carry no cookie session
	and are skipped.
	"""
	request = getattr(frappe.local, "request", None)
	session = getattr(frappe.local, "session", None)
	if request is None or session is None:
		return
	sid, user = session.get("sid"), session.get("user")
	if not sid or sid == "Guest" or not user or user == "Guest" or request.headers.get("Authorization"):
		return
	if frappe.cache.get_value(_session_key(sid), expires=True, use_local_cache=False) is None:
		from frappe.auth import clear_cookies
		from frappe.sessions import delete_session

		delete_session(sid, user=user, reason="Idle timeout")
		clear_cookies()
		frappe.local.session = frappe._dict({"user": "Guest", "sid": "Guest", "data": frappe._dict()})
		frappe.set_user("Guest")
		raise frappe.SessionExpired
	if not is_background_request(request):
		mark_activity(sid, user)


def check_fresh_authentication(user: str, claims: dict, record: dict) -> str:
	"""Decides how an employee's sign-in continues (O-25, review finding Ö2).

	Returns "ok", "force" (restart with `prompt=login`) or "refuse". An employee who had real activity in
	the last hour continues. Otherwise Keycloak must confirm a sign-in made during this very attempt:
	`auth_time` must not be older than the start of the forced attempt.
	"""
	if frappe.db.get_value("User", user, "user_type") != EMPLOYEE_USER_TYPE:
		return "ok"
	if recently_active(user):
		return "ok"
	if not record.get("force_login"):
		return "force"
	auth_time = claims.get("auth_time")
	started = record.get("started_at")
	if isinstance(auth_time, bool) or not isinstance(auth_time, int | float) or not isinstance(started, int):
		return "refuse"
	return "ok" if auth_time >= started - AUTH_TIME_LEEWAY else "refuse"
