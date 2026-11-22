"""Yazma önerileri: önizleme, insan onayı, tek kullanımlık yürütme ve “unknown” kuralı (G-86)."""

import hashlib
import json
import secrets
from typing import Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from frappe.utils import add_to_date, get_datetime, now_datetime, strip_html
from frappe.utils.response import json_handler
from pydantic import Field

from platform_core.yapay_zeka import access, registry, store, versioning
from platform_core.yapay_zeka.errors import ToolDenied

TTL_SECONDS = 600
STATUS_FILTERS = {
	"pending": ("pending",),
	"expired": ("pending", "expired"),
	"rejected": ("rejected",),
	"consumed": ("consumed",),
}
APPROVE_ATTEMPTS = 4
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
	"""Onayı bu önizlemeye bağlayan özet.

	Rastgele bir değer de girer. Böylece model özeti kendi bildiği girdilerden hesaplayamaz.
	Özet yalnız insan ucundan (`get_proposal`) döner.
	"""
	parts = [
		frappe.local.site,
		user,
		tool,
		target_key or "",
		version or "",
		args,
		preview,
		secrets.token_hex(16),
	]
	return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _run_preview(tool: registry.AiTool, arguments: dict) -> dict:
	spec = tool.preview(**arguments)
	if not isinstance(spec, dict) or not isinstance(spec.get("summary"), str):
		raise ToolDenied("internal_error", _("The preview of tool {0} is not valid.").format(tool.name))
	spec.setdefault("action", "app_tool")
	if tool.tool_class == "app" and tool.versioned:
		# The tool asked the layer to guard the target's version. Without all three values the
		# layer could neither lock the row nor compare versions, so the action stops here.
		missing = [key for key in ("target_doctype", "target_name", "target_version") if not spec.get(key)]
		if missing:
			raise ToolDenied(
				"invalid_preview",
				_("The preview of versioned tool {0} must return {1}.").format(tool.name, ", ".join(missing)),
			)
	spec["target_version"] = versioning.token(spec.get("target_version"))
	return spec


def open_proposal(tool: registry.AiTool, arguments: dict) -> tuple[dict, Any]:
	"""Önizleme üretir ve öneri kaydını açar. Hedef kayda hiçbir şey yazılmaz."""
	spec = _run_preview(tool, arguments)
	args_json = _json(arguments)
	# Hedefi olmayan işte (örneğin yeni kayıt) anahtar araç ve girdiden üretilir.
	# Böylece sonucu bilinmeyen iş aynı girdiyle yeniden önerilemez.
	target_key = _target_key(spec.get("target_doctype"), spec.get("target_name")) or _target_key(
		tool.name, args_json
	)
	if store.unresolved_unknown_exists(target_key):
		raise ToolDenied(
			"unresolved_unknown",
			_("An earlier action on this target has an unknown result. A human must resolve it first."),
		)
	preview = {key: spec[key] for key in PREVIEW_KEYS if spec.get(key) is not None}
	preview_json = _json(preview)
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
	return access.human_call("call", "get_proposal", lambda: public(_own(proposal_id)), proposal=proposal_id)


def list_for_human(status: str | None = None, limit: int = 20) -> list[dict]:
	def rows() -> list[dict]:
		if status and status not in STATUS_FILTERS:
			frappe.throw(_("Unknown status."), frappe.ValidationError)
		count = min(max(int(limit), 1), 100)
		# Süresi dolan bekleyen öneri okuma anında `expired` görünür. Bu yüzden süzme iki adımlıdır.
		names = store.proposals_of(frappe.session.user, STATUS_FILTERS.get(status), 500)
		found = (public(store.load_proposal(name)) for name in names)
		return [row for row in found if not status or row["status"] == status][:count]

	return access.human_call("call", "list_proposals", rows)


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
	"""İnsan onayı. Denetimler geçerse işi bu istekte, bir kez yürütür.

	Yarışan bir onay satırı değiştirdiyse veritabanı kilitli okumayı reddeder
	(`frappe/database/mariadb/database.py:27`). O zaman işlem geri alınır ve denetimler
	güncel veriyle yeniden yapılır. Kilit alınmadan önce hiçbir şey yazılmamıştır.
	"""
	access.require_human("approve")
	if store.load_proposal(proposal_id) is None:
		access.record("approve", decision="denied", deny_reason="not_found", tool="approve_proposal")
		frappe.db.commit()  # nosemgrep: 404 yanıtı işlemi geri alır, ret kaydı kalmalı
		raise frappe.DoesNotExistError(_("Proposal not found."))
	for _attempt in range(APPROVE_ATTEMPTS - 1):
		try:
			return _approve(proposal_id, digest)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			frappe.clear_messages()
	return _approve(proposal_id, digest)


def _approve(proposal_id: str, digest: str) -> dict:
	doc = store.load_proposal(proposal_id)
	if doc is None:
		raise frappe.DoesNotExistError(_("Proposal not found."))
	if doc.user != frappe.session.user:
		# Başkasının önerisi yanıtta dönmez. Önizleme o kullanıcının verisini taşır.
		_log("approve", doc, decision="denied", deny_reason="not_owner")
		frappe.db.commit()  # nosemgrep: 403 yanıtı işlemi geri alır, ret kaydı kalmalı
		raise frappe.PermissionError(_("This proposal belongs to another user."))

	# Kilit sırası her istekte aynıdır: önce hedefin bütün önerileri, sonra bu öneri.
	# Sıra değişirse yarışan iki onay birbirini kilitler. Durum kilit altında yeniden okunur.
	siblings = store.lock_target(doc.target_key) if doc.target_key else []
	doc = store.load_proposal(proposal_id, for_update=True)
	if doc.status != "pending":
		return _denied(doc, "not_pending")
	if get_datetime(doc.expires_at) < now_datetime():
		return _denied(doc, "expired", new_status="expired")
	if not isinstance(digest, str) or not secrets.compare_digest(digest, doc.digest):
		return _denied(doc, "digest_mismatch")

	tool = registry.find(doc.tool)
	arguments = json.loads(doc.args_json)
	if tool is None or tool.kind != "write" or not tool.visible():
		return _denied(doc, "not_found", new_status="rejected")

	if any(row.name != doc.name and row.status == "consumed" and row.result == "unknown" for row in siblings):
		return _denied(doc, "unresolved_unknown")

	# Önizleme kilit altında yeniden çalışır. İzin ve kaydın sürümü yürütme anında denetlenir.
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
	except frappe.ValidationError:
		# The preview of an app tool refused the action. Nothing has been written.
		frappe.clear_messages()
		return _denied(doc, "invalid_arguments", new_status="rejected")
	if (spec.get("target_version") or None) != (doc.target_modified or None):
		return _denied(doc, "document_changed", new_status="rejected")
	return _execute(doc, tool, arguments)


def _execute(doc, tool: registry.AiTool, arguments: dict) -> dict:
	# İstekten önce sonuç `unknown` yazılır ve kesinleştirilir (sözleşme 10, kural 7).
	# Bilinçli V-2 istisnası: süreç yarıda ölürse iz kalır ve öneri yeniden kullanılamaz.
	doc.status, doc.result, doc.decided_at = "consumed", "unknown", now_datetime()
	store.save_proposal(doc)
	_log("approve", doc, decision="allowed")
	frappe.db.commit()  # nosemgrep

	committed = []
	frappe.db.after_commit.add(lambda: committed.append(True))

	# Step 1: the layer's own check. It runs only code of this layer and calls no Frappe document
	# method, so nothing outside this transaction can have happened. Only an error here may be
	# recorded as `failed`.
	try:
		prepared = _pre_check(doc, tool, arguments)
	except Exception as error:
		untouched = not committed and not frappe.db.transaction_writes
		return _execution_error(doc, tool, error, result="failed" if untouched else "unknown")

	# ---------------------------------------------------------------------------------------
	# WRITE BOUNDARY. This is the only place that decides between `failed` and `unknown`.
	# From here on code outside the layer's control runs: Frappe document methods (insert,
	# save, submit, cancel, delete) with their hooks, and every function of an app tool,
	# its own `prepare` included. Such code may reach another system or commit. Every error
	# below this line is `unknown`, whatever its type, `ToolDenied` included. A human resolves it.
	# ---------------------------------------------------------------------------------------
	try:
		if tool.tool_class == "app":
			result = tool.handler(tool.prepare(**arguments)) if tool.prepare else tool.handler(**arguments)
		else:
			result = tool.handler(prepared)
	except Exception as error:
		return _execution_error(doc, tool, error, result="unknown")

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
	frappe.db.commit()  # nosemgrep: sonuç kalıcı olmalı
	return {"executed": True, "deny_reason": None, "proposal": public(doc)}


def _pre_check(doc, tool: registry.AiTool, arguments: dict) -> Any:
	"""Run the layer's own check before the write boundary. Return what a built-in write step needs.

	A built-in tool checks the previewed version itself, under a row lock. For an app tool that
	declares `versioned`, the layer locks the target row, runs the preview again and compares
	the version. An app tool's own `prepare` is not part of this check. It runs after the boundary.
	"""
	if tool.tool_class != "app":
		extra = {"expected_version": doc.target_modified} if tool.versioned else {}
		return tool.prepare(**arguments, **extra)
	if tool.versioned:
		spec = _run_preview(tool, arguments)
		store.lock_row(spec["target_doctype"], spec["target_name"])
		# Read again under the lock, then compare with the version the human approved.
		if _run_preview(tool, arguments)["target_version"] != doc.target_modified:
			raise ToolDenied("document_changed", _("The target changed after the preview."))
	return None


def _execution_error(doc, tool: registry.AiTool, error: Exception, *, result: str) -> dict:
	"""Roll back, record the given result and return the outcome of a failed execution."""
	frappe.db.rollback()
	frappe.clear_messages()
	doc = store.load_proposal(doc.name, for_update=True)
	doc.result = result
	doc.error = _error_text(tool, error)
	store.save_proposal(doc)
	_log("execute", doc, decision="error", deny_reason="execution_failed")
	frappe.db.commit()  # nosemgrep: the result must outlive the error response
	return {"executed": False, "deny_reason": "execution_failed", "proposal": public(doc)}


def _error_text(tool: registry.AiTool, error: Exception) -> str:
	"""Kullanıcıya dönen hata metni. Beklenmeyen hatanın ayrıntısı yalnız hata kaydına gider."""
	if isinstance(error, ToolDenied):
		return error.code
	if isinstance(error, frappe.ValidationError | frappe.PermissionError):
		return strip_html(str(error) or type(error).__name__)[:300]
	frappe.log_error(title=f"AI tool {tool.name} failed during execution")
	return "internal_error"


def reject(proposal_id: str) -> dict:
	def run() -> dict:
		doc = _own(proposal_id, for_update=True)
		if doc.status != "pending":
			raise access.WrongState(_("Only a pending proposal can be rejected."))
		doc.status, doc.decided_at = "rejected", now_datetime()
		store.save_proposal(doc)
		_log("reject", doc, decision="allowed")
		return public(doc)

	return access.human_call("reject", "reject_proposal", run, proposal=proposal_id, log_success=False)


def resolve(proposal_id: str, outcome: str) -> dict:
	"""Sonucu bilinmeyen öneriyi insan kararıyla kapatır. Hedef kayda yazmaz."""

	def run() -> dict:
		if outcome not in ("succeeded", "failed"):
			frappe.throw(_("outcome must be succeeded or failed."), frappe.ValidationError)
		doc = _own(proposal_id, for_update=True)
		if doc.status != "consumed" or doc.result != "unknown":
			raise access.WrongState(_("Only a proposal with an unknown result can be resolved."))
		doc.result, doc.decided_at = outcome, now_datetime()
		store.save_proposal(doc)
		_log("resolve", doc, decision="allowed")
		return public(doc)

	return access.human_call("resolve", "resolve_proposal", run, proposal=proposal_id, log_success=False)
