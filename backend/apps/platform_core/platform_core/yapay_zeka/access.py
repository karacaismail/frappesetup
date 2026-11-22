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
	record(stage, tool=tool, decision="denied", deny_reason="not_human_session")
	# Hata yanıtı işlemi geri alır. Ret kaydı kaybolmasın diye burada kesinleştirilir.
	# Bu noktaya kadar istekte başka yazı yoktur.
	frappe.db.commit()  # nosemgrep
	raise frappe.PermissionError(_("This action needs a human session."))


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
		frappe.db.rollback()
		code = next(code for kind, code in codes if isinstance(error, kind))
		record(stage, decision="denied", deny_reason=code, tool=tool, proposal=_existing(proposal))
		frappe.db.commit()  # nosemgrep
		raise
	if log_success:
		record(stage, decision="allowed", tool=tool, proposal=_existing(proposal))
	if frappe.request.method == "GET":
		frappe.db.commit()  # nosemgrep: GET isteği yazıları geri alır
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
			"ip": frappe.local.request_ip,
			"duration_ms": int((time.monotonic() - started) * 1000) if started else None,
		}
	)
