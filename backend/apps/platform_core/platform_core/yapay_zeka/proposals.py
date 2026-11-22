"""Yazma önerileri: önizleme, insan onayı, tek kullanımlık yürütme ve “unknown” kuralı (G-86)."""

import hashlib
import json
from typing import Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from frappe.utils import add_to_date, get_datetime, now_datetime, strip_html
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.response import json_handler
from frappe.utils.synchronization import filelock
from pydantic import Field

from platform_core.yapay_zeka import access, registry, store
from platform_core.yapay_zeka.errors import ToolDenied

TTL_SECONDS = 600
LOCK_TIMEOUT_SECONDS = 10
PREVIEW_KEYS = ("action", "summary", "changes", "details")


class GetProposalArguments(ToolArguments):
	proposal_id: str = Field(min_length=1)


def _json(value: Any) -> str:
	return json.dumps(value, sort_keys=True, default=json_handler, ensure_ascii=False)


def _target_key(doctype: str | None, name: str | None) -> str | None:
	if not doctype or not name:
		return None
	return hashlib.sha256(f"{doctype}\n{name}".encode()).hexdigest()


def _digest(
	user: str, tool: str, target_key: str | None, version: str | None, args: str, preview: str
) -> str:
	parts = [frappe.local.site, user, tool, target_key or "", version or "", args, preview]
	return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _run_preview(tool: registry.AiTool, arguments: dict) -> dict:
	spec = tool.preview(**arguments)
	if not isinstance(spec, dict) or not isinstance(spec.get("summary"), str):
		raise ToolDenied("internal_error", _("The preview of tool {0} is not valid.").format(tool.name))
	spec.setdefault("action", "app_tool")
	return spec


def open_proposal(tool: registry.AiTool, arguments: dict) -> tuple[dict, Any]:
	"""Önizleme üretir ve öneri kaydını açar. Hedef kayda hiçbir şey yazılmaz."""
	spec = _run_preview(tool, arguments)
	target_key = _target_key(spec.get("target_doctype"), spec.get("target_name"))
	if target_key and store.unresolved_unknown_exists(target_key):
		raise ToolDenied(
			"unresolved_unknown",
			_("An earlier action on this target has an unknown result. A human must resolve it first."),
		)
	preview = {key: spec[key] for key in PREVIEW_KEYS if spec.get(key) is not None}
	args_json, preview_json = _json(arguments), _json(preview)
	version = spec.get("target_version")
	doc = store.insert_proposal(
		{
			"user": frappe.session.user,
			"principal": access.principal(),
			"session_id": access.session_id(),
			"tool": tool.name,
			"tool_class": tool.tool_class,
			"target_doctype": spec.get("target_doctype"),
			"target_name": spec.get("target_name"),
			"target_key": target_key,
			"target_modified": version,
			"args_json": args_json,
			"preview_json": preview_json,
			"digest": _digest(frappe.session.user, tool.name, target_key, version, args_json, preview_json),
			"destructive": int(tool.destructive),
			"billable": int(tool.billable),
			"expires_at": add_to_date(now_datetime(), seconds=TTL_SECONDS),
			"status": "pending",
		}
	)
	result = {
		"status": "approval_required",
		"proposal_id": doc.name,
		"preview": json.loads(preview_json),
		"expires_at": str(doc.expires_at),
	}
	return result, doc


def public(doc, *, with_digest: bool = True) -> dict:
	"""Önerinin dışarıya dönen biçimi. Süresi dolan bekleyen öneri `expired` görünür."""
	status = doc.status
	if status == "pending" and get_datetime(doc.expires_at) < now_datetime():
		status = "expired"
	result = {
		"proposal_id": doc.name,
		"status": status,
		"result": doc.result or "",
		"tool": doc.tool,
		"target_doctype": doc.target_doctype,
		"target_name": doc.target_name,
		"destructive": bool(doc.destructive),
		"billable": bool(doc.billable),
		"preview": json.loads(doc.preview_json),
		"expires_at": str(doc.expires_at),
		"result_document": doc.result_document,
		"error": doc.error,
	}
	if with_digest:
		result["digest"] = doc.digest
	return result


def _own(proposal_id: str, *, for_update: bool = False):
	"""Kullanıcının kendi önerisini yükler. Başkasının önerisi izin hatası verir."""
	doc = store.load_proposal(proposal_id, for_update=for_update)
	if doc is None:
		raise frappe.DoesNotExistError(_("Proposal not found."))
	if doc.user != frappe.session.user:
		raise frappe.PermissionError(_("This proposal belongs to another user."))
	return doc


def read_for_model(proposal_id: str) -> dict:
	"""`get_proposal` aracı. Onay özetini dönmez."""
	return public(_own(proposal_id), with_digest=False)


def read_for_human(proposal_id: str) -> dict:
	access.require_human("call", tool="get_proposal")
	return public(_own(proposal_id))


def list_for_human(status: str | None = None, limit: int = 20) -> list[dict]:
	access.require_human("call", tool="list_proposals")
	if status not in (None, "", "pending", "rejected", "expired", "consumed"):
		frappe.throw(_("Unknown status."), frappe.ValidationError)
	limit = min(max(int(limit), 1), 100)
	rows = [public(store.load_proposal(name)) for name in store.proposals_of(frappe.session.user, None, 200)]
	return [row for row in rows if not status or row["status"] == status][:limit]


def _log(stage: str, doc, *, decision: str, deny_reason: str | None = None, **extra) -> None:
	access.record(
		stage,
		decision=decision,
		deny_reason=deny_reason,
		tool=doc.tool,
		tool_class=doc.tool_class,
		target_doctype=doc.target_doctype,
		target_name=doc.target_name,
		proposal=doc.name,
		approval_state=doc.status,
		result=doc.result or None,
		**extra,
	)


def _denied(doc, reason: str, *, new_status: str | None = None) -> dict:
	if new_status:
		doc.status = new_status
		doc.error = reason
		doc.decided_at = now_datetime()
		store.save_proposal(doc)
	_log("approve", doc, decision="denied", deny_reason=reason)
	return {"executed": False, "deny_reason": reason, "proposal": public(doc)}


def approve(proposal_id: str, digest: str) -> dict:
	"""İnsan onayı. Denetimler geçerse işi bu istekte, bir kez yürütür."""
	access.require_human("approve")
	doc = store.load_proposal(proposal_id, for_update=True)
	if doc is None:
		raise frappe.DoesNotExistError(_("Proposal not found."))
	if doc.user != frappe.session.user:
		return _denied(doc, "not_owner")
	if doc.status != "pending":
		return _denied(doc, "not_pending")
	if get_datetime(doc.expires_at) < now_datetime():
		return _denied(doc, "expired", new_status="expired")
	if digest != doc.digest:
		return _denied(doc, "digest_mismatch")

	tool = registry.find(doc.tool)
	arguments = json.loads(doc.args_json)
	if tool is None or tool.kind != "write" or not tool.visible():
		return _denied(doc, "not_found", new_status="rejected")
	# Önizleme yeniden çalışır. Böylece izin ve kaydın sürümü yürütme anında yeniden denetlenir.
	try:
		spec = _run_preview(tool, arguments)
	except ToolDenied as error:
		return _denied(doc, error.code, new_status="rejected")
	except frappe.PermissionError:
		frappe.clear_messages()
		return _denied(doc, "permission", new_status="rejected")
	except frappe.DoesNotExistError:
		frappe.clear_messages()
		return _denied(doc, "document_changed", new_status="rejected")
	if (spec.get("target_version") or None) != (doc.target_modified or None):
		return _denied(doc, "document_changed", new_status="rejected")

	try:
		with filelock(f"yz_target_{doc.target_key or doc.name}", timeout=LOCK_TIMEOUT_SECONDS):
			return _execute(doc, tool, arguments)
	except LockTimeoutError:
		frappe.clear_messages()
		return _denied(doc, "unresolved_unknown")


def _execute(doc, tool: registry.AiTool, arguments: dict) -> dict:
	if doc.target_key and store.unresolved_unknown_exists(doc.target_key, exclude=doc.name):
		return _denied(doc, "unresolved_unknown")

	# İstekten önce sonuç `unknown` yazılır ve kesinleştirilir (sözleşme 10, kural 7).
	# Bilinçli V-2 istisnası: süreç yarıda ölürse iz kalır ve öneri yeniden kullanılamaz.
	doc.status, doc.result, doc.decided_at = "consumed", "unknown", now_datetime()
	store.save_proposal(doc)
	_log("approve", doc, decision="allowed")
	frappe.db.commit()  # nosemgrep

	try:
		result = tool.handler(**arguments)
	except Exception as error:
		frappe.db.rollback()
		frappe.clear_messages()
		doc = store.load_proposal(doc.name, for_update=True)
		doc.result = "failed"
		doc.error = strip_html(str(error) or type(error).__name__)[:500]
		store.save_proposal(doc)
		_log("execute", doc, decision="error", deny_reason="execution_failed")
		frappe.db.commit()  # nosemgrep: sonuç kilit bırakılmadan önce kalıcı olmalı
		return {"executed": False, "deny_reason": "execution_failed", "proposal": public(doc)}

	touched = result.get("name") if isinstance(result, dict) else None
	doc.result = "succeeded"
	doc.result_document = str(touched) if touched else doc.target_name
	store.save_proposal(doc)
	_log(
		"execute",
		doc,
		decision="allowed",
		version=store.latest_version(doc.target_doctype, doc.result_document),
	)
	frappe.db.commit()  # nosemgrep: sonuç kilit bırakılmadan önce kalıcı olmalı
	return {"executed": True, "deny_reason": None, "proposal": public(doc)}


def reject(proposal_id: str) -> dict:
	access.require_human("reject")
	doc = _own(proposal_id, for_update=True)
	if doc.status != "pending":
		frappe.throw(_("Only a pending proposal can be rejected."), frappe.ValidationError)
	doc.status, doc.decided_at = "rejected", now_datetime()
	store.save_proposal(doc)
	_log("reject", doc, decision="allowed")
	return public(doc)


def resolve(proposal_id: str, outcome: str) -> dict:
	"""Sonucu bilinmeyen öneriyi insan kararıyla kapatır. Hedef kayda yazmaz."""
	access.require_human("resolve")
	if outcome not in ("succeeded", "failed"):
		frappe.throw(_("outcome must be succeeded or failed."), frappe.ValidationError)
	doc = _own(proposal_id, for_update=True)
	if doc.status != "consumed" or doc.result != "unknown":
		frappe.throw(_("Only a proposal with an unknown result can be resolved."), frappe.ValidationError)
	doc.result, doc.decided_at = outcome, now_datetime()
	store.save_proposal(doc)
	_log("resolve", doc, decision="allowed")
	return public(doc)
