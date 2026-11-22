"""Version 1 of the mobile sync API."""

import hashlib
import time

import frappe

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


def _registry(name, approved):
	if frappe.conf.get("allow_tests"):
		return getattr(frappe.local, name, approved)
	return approved


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
	result = MobileStore().revoke(identity, installation)
	if revoke_all or result["revoked"]:
		record_revocation(identity.account)
	return result


def _push(identity, body):
	_keys(body, {"installation_id", "operations"})
	_lock_mobile_account(identity)
	store = MobileStore()
	store.require_installation(identity, uuid4_id(body["installation_id"]), for_update=True)
	disabled = frappe.conf.get("mobile_disabled_commands", [])
	if not isinstance(disabled, list) or any(not isinstance(name, str) for name in disabled):
		raise MobileError("invalid_mobile_settings", 503)
	return push(
		store,
		_registry("mobile_commands", COMMANDS),
		identity.site,
		identity.account,
		body["operations"],
		principal=identity.principal,
		disabled_commands=disabled,
	)


def _pull(identity, body):
	_require_enabled_user(identity.account)
	_keys(body, {"installation_id"}, {"limit", "cursor"})
	site_secret = frappe.conf.get("mobile_cursor_key")
	if not isinstance(site_secret, str) or len(site_secret) < 32:
		raise MobileError("cursor_key_unavailable", 503)
	secret = hashlib.sha256(site_secret.encode()).digest()
	installation = uuid4_id(body["installation_id"])
	store = MobileStore()
	store.require_installation(identity, installation)
	if "cursor" in body and not isinstance(body["cursor"], str):
		raise MobileError("invalid_cursor", 410)
	return pull(
		store,
		_registry("mobile_projections", PROJECTIONS),
		secret,
		(identity.site, identity.principal, installation, identity.scope),
		body.get("cursor"),
		body.get("limit", PAGE_SIZE),
		account=identity.account,
		now=int(time.time()),
		inventories=_registry("mobile_inventories", INVENTORIES),
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
