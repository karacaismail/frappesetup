"""Session lifetime rules (PROJE-KAYDI.md O-25).

- The Frappe cookie session ends after 1 hour without activity, for employees and customers.
  Frappe reads the idle limit from System Settings `session_expiry` (frappe/sessions.py:523) and checks
  it on every resume, in the cache (frappe/sessions.py:373) and in the database fallback
  (frappe/sessions.py:499). `apply` writes the limit on install and on every migrate.
- Idle time is measured from real user activity (review finding Ö2). Frappe renews a session on every
  request, background polling included. `before_request` keeps its own activity key per session and per
  user in Redis. Site cache clears preserve those keys. Background requests do not renew them.
- A user who was idle for the limit authenticates again at Keycloak. On the tenant site this holds for
  every user, employee or customer (docs/sozlesmeler.md section 3). The open Keycloak cookie must not skip
  this step: the login restarts with `prompt=login`, and the forced attempt accepts only an `auth_time`
  from that attempt. Customer durations apply only to Press.
"""

import re
import time

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

# System Settings validates hh:mm. Frappe's session parser expects hh:mm:ss.
SYSTEM_SETTINGS_IDLE_TIMEOUT = "01:00"
IDLE_TIMEOUT = f"{SYSTEM_SETTINGS_IDLE_TIMEOUT}:00"
IDLE_SECONDS = 3600
ACTIVITY_PREFIX = "kimlik_activity"
AUTH_TIME_LEEWAY = 30
BACKGROUND_HEADER = "X-Platform-Background"
METHOD_PATH = re.compile(r"^/api/(?:v[12]/)?method/([^/?#]+)")
# Polling and realtime helpers of the desk. They keep a tab alive but are not user activity.
BACKGROUND_METHOD_PREFIXES = (
	"frappe.realtime.",
	"frappe.desk.notifications.",
	"frappe.auth.get_logged_user",
	"frappe.sessions.get",
)


def apply() -> None:
	"""Writes the idle limit into System Settings. Called by `after_install` and `after_migrate`."""
	if frappe.db.get_single_value("System Settings", "session_expiry") != SYSTEM_SETTINGS_IDLE_TIMEOUT:
		# V-1 exception: a single field of a single DocType, no validation side effects are wanted here.
		frappe.db.set_single_value("System Settings", "session_expiry", SYSTEM_SETTINGS_IDLE_TIMEOUT)
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
	return requested_method(request).startswith(BACKGROUND_METHOD_PREFIXES)


def requested_method(request) -> str:
	"""Method name of a request in every form Frappe accepts (merge review Ö2).

	`/api/method/<m>`, `/api/v1/method/<m>`, `/api/v2/method/<m>` and the `cmd` field in the form, the
	query string or a JSON body.
	"""
	path = request.path or ""
	match = METHOD_PATH.match(path)
	if match:
		return match.group(1)
	# Frappe reads `cmd` from the form, the query string and a JSON body into `form_dict`
	# (frappe/app.py:338). Reading `form_dict` covers all three (merge review 2, Ö2).
	return str(frappe.form_dict.get("cmd") or request.form.get("cmd") or request.args.get("cmd") or "")


def _idle_limit_reached(sid: str) -> bool:
	last_activity = frappe.cache.get_value(_session_key(sid), expires=True, use_local_cache=False)
	if last_activity is not None:
		return time.time() - last_activity >= IDLE_SECONDS

	# An expired or missing key may belong to a session from before this hook ran.
	# Creation is a safe baseline: Frappe updates last_updated even on background requests.
	created_at = frappe.session.data.get("creation")
	return not created_at or time_diff_in_seconds(now_datetime(), created_at) >= IDLE_SECONDS


def before_request() -> None:
	"""Ends a cookie session whose last real activity is older than the idle limit.

	Frappe renews `last_updated` on every request, background polling included (frappe/sessions.py:420).
	This hook measures real activity instead. A request with the session cookie is always checked.
	"""
	request = getattr(frappe.local, "request", None)
	session = getattr(frappe.local, "session", None)
	if request is None or session is None:
		return
	sid, user = session.get("sid"), session.get("user")
	# Merge review Ö1: a cookie session is always checked, also when an Authorization header is present.
	# Token identities (service and mobile) carry no cookie session and have no session id here.
	if not sid or sid == "Guest" or not user or user == "Guest":
		return
	if request.cookies.get("sid") != sid:
		return
	if _idle_limit_reached(sid):
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
	"""Decides how a sign-in continues (O-25, review finding Ö2, contract section 3).

	Every user of the tenant site gets the employee durations. Returns "ok", "force" (restart with
	`prompt=login`) or "refuse". A user who had real activity in
	the last hour continues. Otherwise Keycloak must confirm a sign-in made during this very attempt:
	`auth_time` must not be older than the start of the forced attempt.
	"""
	# docs/sozlesmeler.md section 3: on the tenant site every user gets the employee durations.
	if recently_active(user):
		return "ok"
	# Keycloak confirmed a sign-in made during this attempt: that is a fresh authentication.
	if _fresh_for_attempt(claims, record):
		return "ok"
	return "refuse" if record.get("force_login") else "force"


def _fresh_for_attempt(claims: dict, record: dict) -> bool:
	auth_time = claims.get("auth_time")
	started = record.get("started_at")
	if type(auth_time) not in (int, float) or type(started) is not int:
		return False
	return auth_time >= started - AUTH_TIME_LEEWAY
