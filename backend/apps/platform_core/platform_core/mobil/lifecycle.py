"""Account-level serialization and token cutoff for mobile installations."""

import time

import frappe

from .metadata import insert_metadata
from .protocol import TOKEN_CLOCK_SKEW_SECONDS, MobileError

ACCOUNT_STATE = "Mobile Account State"
MAX_ACTIVE_INSTALLATIONS = 20


def lock_account(identity):
	_require_enabled_user(identity.account)

	# Frappe updates the User row during authenticated requests. Keep the mobile
	# lock on our own metadata so a long sync cannot block those updates.
	if _account_state(identity.account) is None:
		# A deletion may have committed after the request opened its read snapshot.
		_require_enabled_user(identity.account, for_update=True)
		insert_metadata(ACCOUNT_STATE, account=identity.account, revoked_through="0", ignore_duplicate=True)
		_account_state(identity.account)


def check_new_installation(identity):
	state = _account_state(identity.account)
	if (
		state is not None
		and int(state.revoked_through) > 0
		and (identity.issued_at is None or identity.issued_at <= int(state.revoked_through))
	):
		raise MobileError("mobile_token_revoked", 403)

	active = frappe.db.get_values(
		"Mobile Installation",
		{"account": identity.account, "revoked": 0},
		"name",
		limit=MAX_ACTIVE_INSTALLATIONS,
		for_update=True,
	)
	if len(active) >= MAX_ACTIVE_INSTALLATIONS:
		raise MobileError("installation_limit", 409)


def lock_revocation_scope(account):
	"""Lock the account's mobile scope without creating state before approval."""
	state = _account_state(account)
	created_at = frappe.db.get_value("User", account, "creation", for_update=state is None)
	if created_at is None:
		raise MobileError("account_unavailable", 404)
	target = state.name if state is not None else account
	cutoff = state.revoked_through if state is not None else "0"
	return target, cutoff, str(created_at)


def record_revocation(account):
	state = _account_state(account)
	cutoff = int(time.time()) + TOKEN_CLOCK_SKEW_SECONDS
	if state is None:
		insert_metadata(ACCOUNT_STATE, account=account, revoked_through=str(cutoff))
	elif cutoff > int(state.revoked_through):
		frappe.db.set_value(ACCOUNT_STATE, state.name, "revoked_through", str(cutoff))


def _require_enabled_user(account, *, for_update=False):
	if not frappe.db.get_value("User", account, "enabled", for_update=for_update):
		raise MobileError("mobile_token_required", 401)


def _account_state(account):
	return frappe.db.get_value(
		ACCOUNT_STATE,
		{"account": account},
		["name", "revoked_through"],
		as_dict=True,
		for_update=True,
	)
