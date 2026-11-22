"""Version 1 of the mobile sync API."""

import hashlib
import time

import frappe

from platform_core.mobil.lifecycle import (
	_require_enabled_user,
	check_new_installation,
	lock_account,
	record_revocation,
)
from platform_core.mobil.protocol import PAGE_SIZE, MobileError, uuid4_id
from platform_core.mobil.request import endpoint_response
from platform_core.mobil.retention import cleanup
from platform_core.mobil.service import COMMANDS, pull, push
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


def _register(identity, body):
	_keys(body, {"installation_id"})
	installation = uuid4_id(body["installation_id"])
	lock_account(identity)
	return MobileStore().install(identity, installation, check_new=check_new_installation)


def _revoke(identity, body):
	revoke_all = body.keys() == {"all"} and body["all"] is True
	installation = None
	if not revoke_all:
		_keys(body, {"installation_id"})
		installation = uuid4_id(body["installation_id"])

	lock_account(identity)
	result = MobileStore().revoke(identity, installation)
	if revoke_all or result["revoked"]:
		record_revocation(identity.account)
	return result


def _push(identity, body):
	_keys(body, {"installation_id", "operations"})
	lock_account(identity)
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
