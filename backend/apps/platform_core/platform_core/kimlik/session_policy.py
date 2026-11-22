"""Session lifetime rules (PROJE-KAYDI.md O-25).

- The Frappe cookie session ends after 1 hour without activity, for employees and customers.
  Frappe reads the idle limit from System Settings `session_expiry` (frappe/sessions.py:523) and checks
  it on every resume, in the cache (frappe/sessions.py:373) and in the database fallback
  (frappe/sessions.py:499). `apply` writes the limit on install and on every migrate.
- An employee (System User) who comes back after the idle limit authenticates again at Keycloak.
  The open Keycloak cookie must not skip this step, so the callback checks the ID token `auth_time`
  and restarts the login with `prompt=login` when it is older than the idle limit.
  Customers keep the Keycloak idle window of 7 days; only their Frappe cookie is 1 hour.
"""

import time

import frappe

IDLE_TIMEOUT = "01:00:00"
IDLE_SECONDS = 3600
EMPLOYEE_USER_TYPE = "System User"


def apply() -> None:
	"""Writes the idle limit into System Settings. Called by `after_install` and `after_migrate`."""
	if frappe.db.get_single_value("System Settings", "session_expiry") != IDLE_TIMEOUT:
		# V-1 exception: a single field of a single DocType, no validation side effects are wanted here.
		frappe.db.set_single_value("System Settings", "session_expiry", IDLE_TIMEOUT)
		frappe.clear_cache()


def needs_fresh_authentication(user: str, claims: dict) -> bool:
	"""True when an employee's Keycloak authentication is older than the idle limit or unknown."""
	if frappe.db.get_value("User", user, "user_type") != EMPLOYEE_USER_TYPE:
		return False
	auth_time = claims.get("auth_time")
	if isinstance(auth_time, bool) or not isinstance(auth_time, int | float):
		return True
	return time.time() - auth_time > IDLE_SECONDS
