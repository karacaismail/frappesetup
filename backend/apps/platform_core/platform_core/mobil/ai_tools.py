"""Mobile administration tools declared through Frappe's AI tool hook."""

from dataclasses import dataclass
from typing import Annotated, Literal

import frappe
from frappe import _
from pydantic import BaseModel, ConfigDict, Field

from .lifecycle import ACCOUNT_STATE, lock_revocation_scope, record_revocation
from .protocol import UUID_PATTERN, MobileError, content_digest
from .retention import cleanup
from .sessions import is_session_closure_pending, pending_session_closures
from .store import MobileStore, _select

ADMIN_ROLE = "System Manager"
TOOL_PATH = "platform_core.mobil.ai_tools"
INSTALLATION = "Mobile Installation"
Account = Annotated[str, Field(min_length=1, max_length=140)]
InstallationId = Annotated[str, Field(pattern=f"^{UUID_PATTERN.pattern}$")]


class AccountArguments(BaseModel):
	model_config = ConfigDict(extra="forbid")
	account: Account


class ListArguments(AccountArguments):
	after: InstallationId | None = None
	limit: int = Field(default=20, ge=1, le=100, strict=True)


class InstallationArguments(BaseModel):
	model_config = ConfigDict(extra="forbid")
	installation_id: InstallationId


class CleanupArguments(BaseModel):
	model_config = ConfigDict(extra="forbid")
	dry_run: Literal[True] = True


@dataclass(frozen=True)
class RevocationPlan:
	account: str
	installation_ids: tuple[str, ...]
	target: str
	version: str


def _require_manager():
	if frappe.session.user in (None, "", "Guest") or ADMIN_ROLE not in frappe.get_roles():
		raise frappe.PermissionError(_("Only a System Manager can administer mobile installations."))


def declarations():
	"""Return plain metadata for the shared AI approval layer."""
	return [
		{
			"name": "list_mobile_installations",
			"description": "List mobile installations for a user.",
			"kind": "read",
			"roles": [ADMIN_ROLE],
			"arguments": f"{TOOL_PATH}.ListArguments",
			"handler": f"{TOOL_PATH}.list_installations",
		},
		{
			"name": "revoke_mobile_installation",
			"description": "Propose revoking one mobile installation.",
			"kind": "write",
			"roles": [ADMIN_ROLE],
			"destructive": True,
			"versioned": True,
			"arguments": f"{TOOL_PATH}.InstallationArguments",
			"handler": f"{TOOL_PATH}.execute_revocation",
			"preview": f"{TOOL_PATH}.preview_revoke_installation",
			"prepare": f"{TOOL_PATH}.prepare_revoke_installation",
		},
		{
			"name": "revoke_all_mobile_installations",
			"description": "Propose revoking all mobile installations for a user.",
			"kind": "write",
			"roles": [ADMIN_ROLE],
			"destructive": True,
			"versioned": True,
			"arguments": f"{TOOL_PATH}.AccountArguments",
			"handler": f"{TOOL_PATH}.execute_revocation",
			"preview": f"{TOOL_PATH}.preview_revoke_all",
			"prepare": f"{TOOL_PATH}.prepare_revoke_all",
		},
		{
			"name": "preview_mobile_cleanup",
			"description": "Count expired mobile records without deleting them.",
			"kind": "read",
			"roles": [ADMIN_ROLE],
			"arguments": f"{TOOL_PATH}.CleanupArguments",
			"handler": f"{TOOL_PATH}.preview_cleanup",
		},
	]


def list_installations(account, after=None, limit=20):
	_require_manager()
	args = ListArguments(account=account, after=after, limit=limit)
	filters = {"account": args.account}
	if args.after is not None:
		filters["name"] = [">", args.after]
	rows = _select(
		INSTALLATION, ["name", "revoked", "session_id"], filters, limit=args.limit + 1, order_by="name asc"
	)
	page = rows[: args.limit]
	pending_sessions = pending_session_closures(row.session_id for row in page)
	return {
		"installations": [
			{
				"installation_id": row.name,
				"revoked": bool(row.revoked),
				"closure_pending": row.session_id in pending_sessions,
			}
			for row in page
		],
		"next_after": rows[args.limit - 1].name if len(rows) > args.limit else None,
	}


def _plan_revocation(account, installation_id=None):
	try:
		target, cutoff, created_at = lock_revocation_scope(account)
	except MobileError as error:
		raise frappe.ValidationError(_("The mobile account is unavailable.")) from error
	rows = MobileStore().revocation_targets(
		account, installation_id, include_revoked=installation_id is not None
	)
	targets = [
		(row.name, bool(row.revoked))
		for row in rows
		if not row.revoked or is_session_closure_pending(row.session_id)
	]
	installation_ids = tuple(name for name, _ in targets)
	if installation_id is not None and not installation_ids:
		raise frappe.ValidationError(_("The mobile installation is unavailable."))
	return RevocationPlan(
		account,
		installation_ids,
		target,
		content_digest([account, created_at, cutoff, targets]),
	)


def prepare_revoke_installation(installation_id):
	_require_manager()
	args = InstallationArguments(installation_id=installation_id)
	account = frappe.db.get_value(INSTALLATION, args.installation_id, "account")
	if not account:
		raise frappe.ValidationError(_("The mobile installation is unavailable."))
	return _plan_revocation(account, args.installation_id)


def prepare_revoke_all(account):
	_require_manager()
	return _plan_revocation(AccountArguments(account=account).account)


def _preview_revocation(plan, summary):
	# The shared layer reruns this preview during approval and checks the version.
	# The mobile scope is already locked, which keeps the approved set stable through execution.
	return {
		"summary": summary,
		"target_doctype": ACCOUNT_STATE,
		"target_name": plan.target,
		"target_version": plan.version,
		"details": {"account": plan.account, "installation_ids": list(plan.installation_ids)},
	}


def preview_revoke_installation(installation_id):
	return _preview_revocation(
		prepare_revoke_installation(installation_id),
		_("Revoke one installation and request Keycloak session closure."),
	)


def preview_revoke_all(account):
	return _preview_revocation(
		prepare_revoke_all(account), _("Revoke all installations and request Keycloak session closure.")
	)


def execute_revocation(plan):
	_require_manager()
	if not isinstance(plan, RevocationPlan):
		raise frappe.ValidationError(_("A prepared mobile revocation is required."))
	try:
		count = MobileStore().revoke_targets(plan.installation_ids)
		record_revocation(plan.account)
	except MobileError as error:
		raise frappe.ValidationError(_("The mobile account is unavailable.")) from error
	return {"name": plan.target, "revoked": count}


def preview_cleanup(dry_run=True):
	_require_manager()
	CleanupArguments(dry_run=dry_run)
	return cleanup(dry_run=True)
