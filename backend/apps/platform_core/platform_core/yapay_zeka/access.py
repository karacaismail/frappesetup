"""Identity type of the request and writing of the action log."""

import hashlib
import json
import secrets
import time
from typing import Any

import frappe
from frappe import _

from platform_core.yapay_zeka import store
from platform_core.yapay_zeka.errors import CONTEXT

HUMAN = "human_session"
AGENT = "agent_token"
OTHER = "other"
GUEST = "guest"
CONVERSATION_HEADER = "Mcp-Conversation-Id"


def principal() -> str:
	"""Return the identity type of the request.

	A human session is only a session that comes with a cookie. A request that carries an
	`Authorization` header does not count as a human session. `agent_token.authenticate_request`
	marks the agent token.
	"""
	if getattr(frappe.local, "yz_agent", None):
		return AGENT
	if frappe.session.user in ("", "Guest"):
		return GUEST
	if frappe.get_request_header("Authorization"):
		return OTHER
	return HUMAN


def require_human(stage: str, *, tool: str | None = None) -> None:
	"""If the request is not from a human session, log the denial and answer 403."""
	if principal() == HUMAN and _csrf_checked():
		return
	record_denial(stage, "not_human_session", tool=tool)
	raise frappe.PermissionError(_("This action needs a human session.", context=CONTEXT))


class TransactionActive(frappe.ValidationError):
	"""The request already holds writes that are not the layer's own."""


def require_clean_transaction() -> None:
	"""Refuse to start work that must commit while the transaction holds earlier writes.

	The layer commits inside the request in a few places. Such a commit must never make
	another caller's pending writes permanent.
	"""
	if frappe.db.transaction_writes:
		frappe.throw(
			_("This action cannot run inside a transaction with pending writes.", context=CONTEXT),
			TransactionActive,
		)


def commit_own_writes() -> None:
	"""The only explicit commit of the layer. Callers make sure the writes are their own."""
	frappe.db.commit()  # nosemgrep: frappe-request-commit


def record_denial(stage: str, deny_reason: str, **fields) -> str:
	"""Write a denial to the log so that it outlives the error response.

	An error response rolls the request back. The pending writes are dropped first, so the
	commit carries the log row and nothing else.
	"""
	frappe.db.rollback()
	name = record(stage, decision="denied", deny_reason=deny_reason, **fields)
	commit_own_writes()
	return name


def _csrf_checked() -> bool:
	"""On a writing request the CSRF header must equal the token in the session.

	Frappe skips this comparison when the session has no token, when `ignore_csrf` is on or
	when there is an allowed referrer (`validate_csrf_token` in `frappe/auth.py`).
	For actions such as approval the comparison is always done here.
	"""
	if frappe.request.method in ("GET", "HEAD", "OPTIONS"):
		return True
	expected = frappe.session.data.get("csrf_token")
	sent = frappe.get_request_header("X-Frappe-CSRF-Token")
	return bool(expected and sent) and secrets.compare_digest(str(sent), str(expected))


class WrongState(frappe.ValidationError):
	"""The proposal is not in the right state for this action."""


def human_call(stage: str, tool: str, action, *, proposal: str | None = None, log_success: bool = True):
	"""Run the action of a human endpoint and write the result to the log.

	An error response and a GET request roll the transaction back (`frappe/app.py`). The log
	row is committed here so that it stays. On a denial nothing else has been written so far.
	"""
	require_human(stage, tool=tool)
	codes = (
		(frappe.DoesNotExistError, "not_found"),
		(WrongState, "not_pending"),
		(frappe.PermissionError, "role_required" if proposal is None else "not_owner"),
		(frappe.ValidationError, "invalid_arguments"),
	)
	try:
		result = action()
	except tuple(kind for kind, _code in codes) as error:
		code = next(code for kind, code in codes if isinstance(error, kind))
		record_denial(stage, code, tool=tool, proposal=_existing(proposal))
		raise
	# A read request (GET) writes to the log only when it is denied. A successful read leaves no
	# row and makes no commit, so another site cannot make the browser fill the log.
	if log_success and frappe.request.method != "GET":
		record(stage, decision="allowed", tool=tool, proposal=_existing(proposal))
	return result


def _existing(proposal: str | None) -> str | None:
	return proposal if proposal and store.load_proposal(proposal) is not None else None


def args_hash(arguments: Any) -> str:
	text = json.dumps(arguments, sort_keys=True, default=str, ensure_ascii=False)
	return hashlib.sha256(text.encode()).hexdigest()


def session_id() -> str | None:
	"""SHA-256 of the conversation id the client sent. The id itself is never stored.

	A client may put a credential into this header by mistake. Rows of one conversation still
	share the same value, so they can be matched.
	"""
	value = frappe.get_request_header(CONVERSATION_HEADER) if frappe.request else None
	return hashlib.sha256(value.encode()).hexdigest() if value else None


def record(
	stage: str,
	*,
	decision: str,
	tool: str | None = None,
	tool_class: str | None = None,
	deny_reason: str | None = None,
	target_doctype: str | None = None,
	target_name: str | None = None,
	arguments: Any = None,
	proposal: str | None = None,
	approval_state: str | None = None,
	result: str | None = None,
	version: str | None = None,
	started: float | None = None,
	user: str | None = None,
	principal_type: str | None = None,
) -> str:
	"""Create an "AI Action Log" record. A digest of the input is written, not the input itself."""
	return store.insert_log(
		{
			"user": user or frappe.session.user,
			"principal": principal_type or principal(),
			"session_id": session_id(),
			"client_info": getattr(frappe.local, "yz_client_info", None),
			"stage": stage,
			"tool": tool,
			"tool_class": tool_class,
			"target_doctype": (target_doctype or "")[:140] or None,
			"target_name": (str(target_name) if target_name else "")[:140] or None,
			"args_hash": args_hash(arguments) if arguments is not None else None,
			"decision": decision,
			"deny_reason": deny_reason,
			"proposal": proposal,
			"approval_state": approval_state,
			"result": result,
			"version": version,
			"ip": getattr(frappe.local, "request_ip", None),
			"duration_ms": int((time.monotonic() - started) * 1000) if started else None,
		}
	)
