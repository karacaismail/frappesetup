"""İsteğin kimlik türü ve işlem günlüğü yazımı."""

import hashlib
import json
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
	"""Yazan istekte oturumun CSRF belirteci olmalı.

	Frappe başlığı yalnız oturumda belirteç varsa doğrular (`frappe/auth.py`). Belirteci
	olmayan oturumda doğrulama atlanır. Onay gibi işlerde bu boşluk burada kapatılır.
	"""
	if frappe.request.method in ("GET", "HEAD", "OPTIONS"):
		return True
	return bool(frappe.session.data.get("csrf_token"))


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
