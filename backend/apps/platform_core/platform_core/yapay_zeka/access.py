"""İsteğin kimlik türü ve işlem günlüğü yazımı."""

import hashlib
import json
import secrets
import time
from typing import Any

import frappe
from frappe import _

from platform_core.yapay_zeka import store

HUMAN = "human_session"
AGENT = "agent_token"
OTHER = "other"
GUEST = "guest"
CONVERSATION_HEADER = "Mcp-Conversation-Id"


def principal() -> str:
	"""İsteğin kimlik türünü döner.

	İnsan oturumu yalnız çerezle gelen oturumdur. `Authorization` başlığı taşıyan istek
	insan oturumu sayılmaz. Aracı belirtecini `agent_token.authenticate_request` işaretler.
	"""
	if getattr(frappe.local, "yz_agent", None):
		return AGENT
	if frappe.session.user in ("", "Guest"):
		return GUEST
	if frappe.get_request_header("Authorization"):
		return OTHER
	return HUMAN


def require_human(stage: str, *, tool: str | None = None) -> None:
	"""İstek insan oturumundan gelmediyse reddi günlüğe yazar ve 403 verir."""
	if principal() == HUMAN and _csrf_checked():
		return
	record_denial(stage, "not_human_session", tool=tool)
	raise frappe.PermissionError(_("This action needs a human session."))


class TransactionActive(frappe.ValidationError):
	"""The request already holds writes that are not the layer's own."""


def require_clean_transaction() -> None:
	"""Refuse to start work that must commit while the transaction holds earlier writes.

	The layer commits inside the request in a few places. Such a commit must never make
	another caller's pending writes permanent.
	"""
	if frappe.db.transaction_writes:
		frappe.throw(_("This action cannot run inside a transaction with pending writes."), TransactionActive)


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
	"""Yazan istekte CSRF başlığı oturumdaki belirteçle aynı olmalı.

	Frappe bu karşılaştırmayı oturumda belirteç yoksa, `ignore_csrf` açıksa ya da
	izinli yönlendiren varsa atlar (`frappe/auth.py` içinde `validate_csrf_token`).
	Onay gibi işlerde karşılaştırma burada her zaman yapılır.
	"""
	if frappe.request.method in ("GET", "HEAD", "OPTIONS"):
		return True
	expected = frappe.session.data.get("csrf_token")
	sent = frappe.get_request_header("X-Frappe-CSRF-Token")
	return bool(expected and sent) and secrets.compare_digest(str(sent), str(expected))


class WrongState(frappe.ValidationError):
	"""Öneri bu iş için uygun durumda değil."""


def human_call(stage: str, tool: str, action, *, proposal: str | None = None, log_success: bool = True):
	"""İnsan ucunun işini çalıştırır ve sonucu günlüğe yazar.

	Hata yanıtı ve GET isteği işlemi geri alır (`frappe/app.py`). Günlük kaydı kalsın diye
	kayıt burada kesinleştirilir. Ret durumunda bu noktaya kadar başka yazı yoktur.
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
	if frappe.request.method == "GET":
		# Frappe rolls a GET request back. A read has no writes of its own to keep, so the
		# transaction is emptied first and the commit carries only the log row.
		frappe.db.rollback()
	if log_success:
		record(stage, decision="allowed", tool=tool, proposal=_existing(proposal))
	if frappe.request.method == "GET":
		commit_own_writes()
	return result


def _existing(proposal: str | None) -> str | None:
	return proposal if proposal and store.load_proposal(proposal) is not None else None


def args_hash(arguments: Any) -> str:
	text = json.dumps(arguments, sort_keys=True, default=str, ensure_ascii=False)
	return hashlib.sha256(text.encode()).hexdigest()


def session_id() -> str | None:
	value = frappe.get_request_header(CONVERSATION_HEADER) if frappe.request else None
	return value[:140] if value else None


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
	"""“AI Action Log” kaydı açar. Girdinin kendisi değil, özeti yazılır."""
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
