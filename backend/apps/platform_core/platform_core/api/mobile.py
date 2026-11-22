"""Version 1 of the mobile sync API."""

import hashlib
import time
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone

from platform_core.mobil.lifecycle import (
	_require_enabled_user,
	check_new_installation,
	lock_account,
	lock_revocation_scope,
	record_revocation,
)
from platform_core.mobil.protocol import PAGE_SIZE, MobileError, uuid4_id
from platform_core.mobil.request import endpoint_response, identity_sync_response
from platform_core.mobil.retention import cleanup
from platform_core.mobil.service import COMMANDS, pull, push
from platform_core.mobil.sessions import require_active_session
from platform_core.mobil.store import MobileStore

# The shared request guard and each action check the installation, record or
# administrator permission. The static rule cannot follow endpoint_response.
# Populate only when a record type and its server-defined projection are approved.
PROJECTIONS = {}
INVENTORIES = {}
IDLE_LIMIT_SECONDS = 3600


def _keys(body, required, optional=()):
	if not required <= body.keys() or body.keys() - required - set(optional):
		raise MobileError("invalid_request")


def _lock_mobile_account(identity):
	lock_account(identity)
	sid = getattr(identity, "sid", None)
	if sid is not None:
		require_active_session(sid, for_update=True)


def _register(identity, body):
	_keys(body, {"installation_id"})
	installation = uuid4_id(body["installation_id"])
	_lock_mobile_account(identity)
	return MobileStore().install(identity, installation, check_new=check_new_installation)


def _revoke(identity, body):
	revoke_all = body.keys() == {"all"} and body["all"] is True
	installation = None
	if not revoke_all:
		_keys(body, {"installation_id"})
		installation = uuid4_id(body["installation_id"])

	_lock_mobile_account(identity)
	store = MobileStore()
	_require_recent_revoker(identity, installation, store)
	result = store.revoke(identity, installation)
	if revoke_all or result["revoked"]:
		record_revocation(identity.account)
	return result


def _require_recent_activity(identity, row):
	bound_at = int(row.session_bound_at or 0)
	if identity.scope == "mobile" and identity.auth_time < bound_at:
		raise MobileError("reauthentication_required", 401)
	last_activity = max(int(row.last_user_activity_at or 0), bound_at)
	if not last_activity:
		last_activity = int(row.creation.replace(tzinfo=ZoneInfo(get_system_timezone())).timestamp())
	if int(time.time()) - last_activity >= IDLE_LIMIT_SECONDS:
		raise MobileError("reauthentication_required", 401)


def _require_recent_revoker(identity, target, store):
	if identity.scope != "mobile" or target == identity.installation:
		return
	row = store.require_installation(identity, identity.installation, for_update=True)
	_require_recent_activity(identity, row)


def _list_installations(identity, body):
	_keys(body, set(), {"after"})
	_require_enabled_user(identity.account)
	after = uuid4_id(body["after"]) if "after" in body else None
	return MobileStore().list_owned_installations(identity, after)


def _revoke_installation(identity, body):
	_keys(body, {"installation_id"})
	installation = uuid4_id(body["installation_id"])
	_lock_mobile_account(identity)
	store = MobileStore()
	_require_recent_revoker(identity, installation, store)
	return store.revoke_owned_installation(identity, installation)


def _activity(identity, body):
	_keys(body, {"installation_id"})
	_lock_mobile_account(identity)
	installation = uuid4_id(body["installation_id"])
	row = MobileStore().require_installation(identity, installation, for_update=True)
	_require_recent_activity(identity, row)
	activity_at = int(time.time())
	frappe.db.set_value("Mobile Installation", installation, "last_user_activity_at", str(activity_at))
	return {"last_user_activity_at": activity_at}


def _push(identity, body, *, commands=None):
	_keys(body, {"installation_id", "operations"})
	_lock_mobile_account(identity)
	store = MobileStore()
	row = store.require_installation(identity, uuid4_id(body["installation_id"]), for_update=True)
	_require_recent_activity(identity, row)
	disabled = frappe.conf.get("mobile_disabled_commands", [])
	if not isinstance(disabled, list) or any(not isinstance(name, str) for name in disabled):
		raise MobileError("invalid_mobile_settings", 503)
	return push(
		store,
		COMMANDS if commands is None else commands,
		identity.site,
		identity.account,
		body["operations"],
		principal=identity.principal,
		disabled_commands=disabled,
	)


def _pull(identity, body, *, projections=None, inventories=None):
	_require_enabled_user(identity.account)
	_keys(body, {"installation_id"}, {"limit", "cursor"})
	installation = uuid4_id(body["installation_id"])
	store = MobileStore()
	row = store.require_installation(identity, installation)
	_require_recent_activity(identity, row)
	site_secret = frappe.conf.get("mobile_cursor_key")
	if not isinstance(site_secret, str) or len(site_secret) < 32:
		raise MobileError("cursor_key_unavailable", 503)
	secret = hashlib.sha256(site_secret.encode()).digest()
	if "cursor" in body and not isinstance(body["cursor"], str):
		raise MobileError("invalid_cursor", 410)
	return pull(
		store,
		PROJECTIONS if projections is None else projections,
		secret,
		(identity.site, identity.principal, installation, identity.scope),
		body.get("cursor"),
		body.get("limit", PAGE_SIZE),
		account=identity.account,
		now=int(time.time()),
		inventories=INVENTORIES if inventories is None else inventories,
	)


def _cleanup(identity, body):
	_keys(body, set(), {"dry_run"})
	if "System Manager" not in frappe.get_roles(identity.account):
		raise MobileError("cleanup_forbidden", 403)
	return cleanup(dry_run=body.get("dry_run", False))


def _linked_account(issuer, subject):
	if not frappe.db.exists("DocType", "Platform Identity Link"):
		raise MobileError("mobile_schema_unavailable", 503)
	return frappe.db.get_value("Platform Identity Link", {"issuer": issuer, "subject": subject}, "user")


def _revoke_user_installations(body):
	account = _linked_account(body["issuer"], body["subject"])
	if not account:
		raise MobileError("IdentityNotFound", 404)
	try:
		_, cutoff, _ = lock_revocation_scope(account)
	except MobileError as error:
		if error.code == "account_unavailable":
			raise MobileError("IdentityNotFound", 404) from error
		raise
	count, newly_revoked = MobileStore().revoke_account_installations(account)
	if newly_revoked or int(cutoff) == 0:
		record_revocation(account)
	return {"revoked": count}


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_register():
	return endpoint_response("v1_register", _register)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_revoke():
	return endpoint_response("v1_revoke", _revoke)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_activity():
	return endpoint_response("v1_activity", _activity)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_push():
	return endpoint_response("v1_push", _push)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_pull():
	return endpoint_response("v1_pull", _pull)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_cleanup():
	return endpoint_response("v1_cleanup", _cleanup)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def revoke_user_installations():
	return identity_sync_response(_revoke_user_installations)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_list_installations():
	return endpoint_response("v1_list_installations", _list_installations)


@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
def v1_revoke_installation():
	return endpoint_response("v1_revoke_installation", _revoke_installation)
