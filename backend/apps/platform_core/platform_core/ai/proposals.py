"""Write proposals: preview, human approval, single-use execution and the "unknown" rule (G-86)."""

import hashlib
import json
import secrets
from typing import Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from frappe.utils import add_to_date, get_datetime, now_datetime
from frappe.utils.response import json_handler
from pydantic import Field

from platform_core.ai import (
	access,
	fields,
	policy,
	registry,
	risk,
	schema_check,
	store,
	timestamps,
	versioning,
)
from platform_core.ai.errors import CONTEXT, ToolDenied, log_tool_error, traceback_without_text
from platform_core.ai.tools import results

TTL_SECONDS = 600
# An R3 proposal runs only after a second person approves it too (AJA-1003).
TWO_PERSON_LEVEL = "R3"
AWAITING = "awaiting_second_approval"
# States in which `approve` may still act. Both run out at `expires_at`.
OPEN_STATES = ("pending", AWAITING)
STATUS_FILTERS = {
	"pending": ("pending",),
	AWAITING: (AWAITING,),
	"expired": ("pending", AWAITING, "expired"),
	"rejected": ("rejected",),
	"consumed": ("consumed",),
}
APPROVE_ATTEMPTS = 4
# Paging by offset scans the skipped rows. The list is for a human's recent proposals.
MAX_LIST_START = 10_000
# Proposals that wait for a second approval live at most `TTL_SECONDS`. The waiting list reads at
# most this many of them and keeps those the reader may approve.
MAX_SECOND_APPROVAL_SCAN = 500
# Upper bounds of the two texts a human endpoint takes. A name is at most 140 characters in Frappe.
MAX_ID_CHARS = 140
MAX_DIGEST_CHARS = 128
PREVIEW_KEYS = ("action", "summary", "changes", "details")
# The permission a second person needs on the target, by the action of the preview (AJA-1003).
# Other actions (`update`, `app_tool`, `admin`) need write permission.
ACTION_PERMISSION = {"create": "create", "submit": "submit", "cancel": "cancel", "delete": "delete"}


class GetProposalArguments(ToolArguments):
	proposal_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)


def _json(value: Any) -> str:
	return json.dumps(value, sort_keys=True, default=json_handler, ensure_ascii=False)


# The canonical JSON form the layer stores and compares.
canonical = _json


def _target_key(doctype: str | None, name: str | None) -> str | None:
	if not doctype or not name:
		return None
	return hashlib.sha256(f"{doctype}\n{name}".encode()).hexdigest()


def _digest(
	user: str, tool: str, target_key: str | None, version: str | None, args: str, preview: str
) -> str:
	"""The digest that binds the approval to this preview.

	A random value goes in too. So the model cannot compute the digest from inputs it knows.
	The digest is returned only from the human endpoint (`get_proposal`).
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


PREVIEW_ACTIONS = frozenset({"create", "update", "submit", "cancel", "delete", "app_tool", "admin"})
CHANGE_KEYS = frozenset({"fieldname", "label", "old", "new"})


def preview_problems(spec: dict) -> list[str]:
	"""Check a preview against the published preview schema. Return what is wrong with it."""
	preview = {key: spec[key] for key in PREVIEW_KEYS if spec.get(key) is not None}
	preview.setdefault("action", "app_tool")
	problems = schema_check.problems(preview, results.PREVIEW, "preview")
	if not isinstance(spec.get("summary"), str) or not spec["summary"].strip():
		problems.append("preview.summary must be a text")
	for index, change in enumerate(preview.get("changes") or []):
		if isinstance(change, dict) and set(change) - CHANGE_KEYS:
			unknown = ", ".join(sorted(set(change) - CHANGE_KEYS))
			problems.append(f"preview.changes[{index}] has unknown keys: {unknown}")
	return problems


def _guards_row(tool: registry.AiTool) -> bool:
	"""An app tool that declares `versioned` asks the layer to guard the target row itself."""
	return tool.tool_class == "app" and tool.versioned


def preview_digest(spec: dict, row_stamp: str | None = None) -> str:
	"""Digest of everything the human approves: the whole preview and the target it is aimed at.

	An approval is valid only while a fresh preview gives the same digest. `row_stamp` is the
	layer's own reading of the target row. At execution it comes from the locking read.
	"""
	shown = {key: spec[key] for key in PREVIEW_KEYS if spec.get(key) is not None}
	shown["target"] = [spec.get("target_doctype"), spec.get("target_name"), row_stamp]
	return hashlib.sha256(_json(shown).encode()).hexdigest()


def _row_stamp(tool: registry.AiTool, spec: dict) -> str | None:
	return store.row_stamp(spec["target_doctype"], spec["target_name"]) if _guards_row(tool) else None


def _run_preview(tool: registry.AiTool, arguments: dict) -> dict:
	spec = tool.preview(**arguments)
	if not isinstance(spec, dict):
		raise ToolDenied(
			"invalid_preview",
			_("The preview of tool {0} must be an object.", context=CONTEXT).format(tool.name),
		)
	spec.setdefault("action", "app_tool")
	# The preview is what the human approves. It is stored only if it follows the preview schema.
	problems = preview_problems(spec)
	if problems:
		raise ToolDenied(
			"invalid_preview",
			_("The preview of tool {0} is not valid: {1}", context=CONTEXT).format(
				tool.name, "; ".join(problems)
			),
		)
	if tool.tool_class == "app" and tool.versioned:
		# The tool asked the layer to guard the target's version. Without all three values the
		# layer could neither lock the row nor compare versions, so the action stops here.
		missing = [key for key in ("target_doctype", "target_name", "target_version") if not spec.get(key)]
		if missing:
			raise ToolDenied(
				"invalid_preview",
				_("The preview of versioned tool {0} must return {1}.", context=CONTEXT).format(
					tool.name, ", ".join(missing)
				),
			)
	spec["target_version"] = versioning.token(spec.get("target_version"))
	return spec


def open_proposal(tool: registry.AiTool, arguments: dict, *, source=None) -> tuple[dict, Any]:
	"""Build the preview and open the proposal record. Nothing is written to the target record.

	`source` is the applied proposal a revert proposal undoes (AJA-1002). The revert's level is
	at least the source's level.
	"""
	# The stored input is canonical JSON. The preview is built from that same form, so the
	# preview made at approval, from the stored input, lists its changes in the same order.
	args_json = _json(arguments)
	arguments = json.loads(args_json)
	spec = _run_preview(tool, arguments)
	# For an action without a target (for example a new record) the key is built from the
	# tool and the input. So an action with an unknown result cannot be proposed again with
	# the same input.
	target_key = _target_key(spec.get("target_doctype"), spec.get("target_name")) or _target_key(
		tool.name, args_json
	)
	if store.unresolved_unknown_exists(target_key):
		raise ToolDenied(
			"unresolved_unknown",
			_(
				"An earlier action on this target has an unknown result. A human must resolve it first.",
				context=CONTEXT,
			),
		)
	preview = {key: spec[key] for key in PREVIEW_KEYS if spec.get(key) is not None}
	preview_json = _json(preview)
	version = spec.get("target_version")
	level = risk.level(tool)
	if source is not None:
		level = risk.higher(level, source.risk_level or "R0")
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
			"preview_digest": preview_digest(spec, _row_stamp(tool, spec)),
			"digest": _digest(frappe.session.user, tool.name, target_key, version, args_json, preview_json),
			"destructive": int(tool.destructive),
			"billable": int(tool.billable),
			# From the tool and the source proposal only. The model's arguments never reach this value.
			"risk_level": level,
			"source_proposal": source.name if source else None,
			"expires_at": add_to_date(now_datetime(), seconds=TTL_SECONDS),
			"status": "pending",
		}
	)
	result = {
		"status": "approval_required",
		"proposal_id": doc.name,
		"risk_level": doc.risk_level,
		"preview": json.loads(preview_json),
		"expires_at": timestamps.iso(doc.expires_at),
		"created_at": timestamps.iso(doc.creation),
	}
	return result, doc


def public(doc, *, with_digest: bool = True) -> dict:
	"""The outward form of the proposal. A pending proposal past its time shows as `expired`."""
	status = doc.status
	if status in OPEN_STATES and get_datetime(doc.expires_at) < now_datetime():
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
		"risk_level": doc.risk_level,
		"source_proposal": doc.get("source_proposal") or None,
		"preview": json.loads(doc.preview_json),
		"expires_at": timestamps.iso(doc.expires_at),
		"created_at": timestamps.iso(doc.creation),
		"result_document": doc.result_document,
		"error": doc.error,
		"first_approved_at": timestamps.iso(doc.first_approved_at),
		"second_approver": doc.second_approver or None,
		"second_approved_at": timestamps.iso(doc.second_approved_at),
	}
	if with_digest:
		result["digest"] = doc.digest
	return result


def check_proposal_id(proposal_id: object) -> None:
	"""Refuse an id that cannot be a proposal's name, before it reaches the database."""
	if not isinstance(proposal_id, str) or not 0 < len(proposal_id) <= MAX_ID_CHARS:
		frappe.throw(_("Proposal not found.", context=CONTEXT), frappe.ValidationError)


def _own(proposal_id: str, *, for_update: bool = False):
	"""Load the user's own proposal. Another user's proposal raises a permission error."""
	check_proposal_id(proposal_id)
	doc = store.load_proposal(proposal_id, for_update=for_update)
	if doc is None:
		raise frappe.DoesNotExistError(_("Proposal not found.", context=CONTEXT))
	if doc.user != frappe.session.user:
		raise frappe.PermissionError(_("This proposal belongs to another user.", context=CONTEXT))
	return doc


# The owner check, for the revert endpoint of `platform_core.ai.revert`.
own = _own


def read_for_model(proposal_id: str) -> dict:
	"""The `get_proposal` tool. Does not return the approval digest."""
	return public(_own(proposal_id), with_digest=False)


def read_for_human(proposal_id: str) -> dict:
	def read():
		if proposal_id == "":
			raise frappe.DoesNotExistError(_("Proposal not found.", context=CONTEXT))
		return public(_own(proposal_id))

	return access.human_call("call", "plt_get_proposal", read, proposal=proposal_id)


def list_for_human(status: str | None = None, limit: int = 20, start: int = 0) -> dict:
	"""One page of the user's proposals, newest first. The database filters and pages."""

	def page() -> dict:
		if status and status not in STATUS_FILTERS:
			frappe.throw(_("Unknown status.", context=CONTEXT), frappe.ValidationError)
		if not 0 <= int(start) <= MAX_LIST_START:
			frappe.throw(
				_("start must be between 0 and {0}.", context=CONTEXT).format(MAX_LIST_START),
				frappe.ValidationError,
			)
		count = min(max(int(limit), 1), 100)
		rows = store.proposals_of(frappe.session.user, status or None, int(start), count + 1)
		return {"proposals": [public(row) for row in rows[:count]], "has_next_page": len(rows) > count}

	return access.human_call("call", "list_proposals", page)


def needs_second_approval(doc) -> bool:
	return doc.risk_level == TWO_PERSON_LEVEL


def second_approver_problem(doc, tools: dict | None = None) -> str | None:
	"""Why the session user may not give the second approval of `doc`. None if the user may.

	The rule is in the decision note, section 7, "Second approval of R3". The second person is
	an enabled user of this site, is not the owner, may use the tool and may write the target
	record. The person may also read every field the preview shows (AJA-1077). Without a target record the person needs the permission on the target DocType.
	A create, submit, cancel or delete needs that permission, not only write.
	Nobody holds write permission on the layer's own records. For those the tool's own role
	check decides. `tools` maps tool names to tools, so a list reads the registry only once.
	"""
	user = frappe.session.user
	if user == doc.user:
		return "second_approver_required"
	if user in ("", "Guest") or not store.user_enabled(user):
		return "not_second_approver"
	tool = tools.get(doc.tool) if tools is not None else registry.find(doc.tool)
	doctype, name = doc.target_doctype, doc.target_name
	if tool is None or not tool.visible() or not doctype:
		return "not_second_approver"
	if doctype in policy.LAYER_DOCTYPES:
		return None
	target = name if name and store.document_exists(doctype, name) else None
	preview = json.loads(doc.preview_json or "{}")
	ptype = ACTION_PERMISSION.get(preview.get("action"), "write")
	if not frappe.has_permission(doctype, ptype, doc=target, user=user):
		return "not_second_approver"
	if not _preview_readable(doctype, preview):
		# The owner built the preview. It may show a field this person may not read (AJA-1077).
		return "not_second_approver"
	return None


def _preview_readable(doctype: str, preview: dict) -> bool:
	"""Whether the session user may read every field of `doctype` the preview shows.

	A change that names a field of the target DocType needs read permission on it, permission
	level and secret fields included. For a child table field every row field counts too.
	A name that is no field of the DocType (for example `title.bold` of a field property) shows
	no record value.
	"""
	meta = fields.get_meta(doctype)
	can_read = fields.readable(meta)
	for change in preview.get("changes") or []:
		if not isinstance(change, dict):
			return False
		field = meta.get_field(change.get("fieldname") or "")
		if field is None:
			continue
		if field.fieldname not in can_read:
			return False
		if field.fieldtype in ("Table", "Table MultiSelect") and not _rows_readable(
			frappe.get_meta(field.options), doctype, change
		):
			return False
	return True


def _rows_readable(child_meta, parenttype: str, change: dict) -> bool:
	can_read = fields.readable(child_meta, parenttype)
	for value in (change.get("old"), change.get("new")):
		for row in value if isinstance(value, list) else []:
			if not isinstance(row, dict):
				continue
			if any(child_meta.get_field(key) is not None and key not in can_read for key in row):
				return False
	return True


def list_second_approvals_for_human(limit: int = 20, start: int = 0) -> dict:
	"""R3 proposals of other users that the session user may approve as the second person.

	Each row carries the digest. The second person sends it back with the approval, as the owner
	does. A row is shown only to a person who may write the target and read every field the
	preview shows (AJA-1077).
	"""

	def page() -> dict:
		if not 0 <= int(start) <= MAX_LIST_START:
			frappe.throw(
				_("start must be between 0 and {0}.", context=CONTEXT).format(MAX_LIST_START),
				frappe.ValidationError,
			)
		count = min(max(int(limit), 1), 100)
		tools = {tool.name: tool for tool in registry.all_tools()}
		rows = [
			row
			for row in store.awaiting_second_approval(frappe.session.user, MAX_SECOND_APPROVAL_SCAN)
			if second_approver_problem(row, tools) is None
		]
		chosen = rows[int(start) : int(start) + count + 1]
		return {"proposals": [public(row) for row in chosen[:count]], "has_next_page": len(chosen) > count}

	return access.human_call("call", "list_second_approvals", page)


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


def _preview_refused(doc, reason: str) -> dict:
	"""Reject a proposal whose preview failed at approval. Undo whatever the preview wrote first.

	An app tool's preview is app code. If it wrote something before it raised, a normal end of
	the request would commit that write. So the transaction is rolled back and the proposal is
	read again under its lock before the rejection is stored.
	"""
	frappe.db.rollback()
	frappe.clear_messages()
	return _denied(store.load_proposal(doc.name, for_update=True), reason, new_status="rejected")


def approve(proposal_id: str, digest: str) -> dict:
	"""Human approval. If the checks pass, executes the action once, in this request.

	If a racing approval changed the row, the database refuses the locked read
	(`frappe/database/mariadb/database.py:27`). Then the transaction is rolled back and the
	checks are done again with current data. Nothing has been written before the lock is taken.
	"""
	access.require_human("approve")
	check_proposal_id(proposal_id)
	if not isinstance(digest, str) or len(digest) > MAX_DIGEST_CHARS:
		frappe.throw(_("The digest is not valid.", context=CONTEXT), frappe.ValidationError)
	if frappe.db.transaction_writes:
		# Approval commits inside the request. It must not make foreign pending writes permanent.
		access.record_denial("approve", "transaction_active", tool="approve_proposal")
		access.require_clean_transaction()
	if store.load_proposal(proposal_id) is None:
		access.record_denial("approve", "not_found", tool="approve_proposal")
		raise frappe.DoesNotExistError(_("Proposal not found.", context=CONTEXT))
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
		raise frappe.DoesNotExistError(_("Proposal not found.", context=CONTEXT))
	user = frappe.session.user
	second = doc.user != user and doc.status == AWAITING
	if doc.user != user and not second:
		# Another user's proposal is not returned in the response. The preview carries that
		# user's data.
		_refuse(doc, "not_owner", _("This proposal belongs to another user.", context=CONTEXT))
	if second and second_approver_problem(doc):
		# Only a person who may write the target sees or approves the proposal of another user.
		_refuse(doc, "not_second_approver", _("You may not approve this proposal.", context=CONTEXT))

	# The lock order is the same in every request: first all proposals of the target, then this
	# proposal. If the order changes, two racing approvals lock each other. The status is read
	# again under the lock.
	siblings = store.lock_target(doc.target_key) if doc.target_key else []
	doc = store.load_proposal(proposal_id, for_update=True)
	if doc.status not in OPEN_STATES or (doc.status == "pending" and second):
		return _denied(doc, "not_pending")
	if doc.status == AWAITING and doc.user == user:
		# The owner's second approval counts as one approval. The proposal waits on.
		return _denied(doc, "second_approver_required")
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

	# The preview runs again under the lock. Permission and the record's version are checked at
	# execution time.
	try:
		spec = _run_preview(tool, arguments)
	except frappe.PermissionError:
		if second:
			# The second person may not do this action. That person cannot end the owner's
			# proposal: the proposal keeps waiting for another second person.
			frappe.clear_messages()
			_refuse(doc, "not_second_approver", _("You may not approve this proposal.", context=CONTEXT))
		return _preview_refused(doc, "permission")
	except ToolDenied as error:
		return _preview_refused(doc, error.code)
	except frappe.DoesNotExistError:
		return _preview_refused(doc, "document_changed")
	except frappe.ValidationError:
		# The preview of an app tool refused the action.
		return _preview_refused(doc, "invalid_arguments")
	if (spec.get("target_version") or None) != (doc.target_modified or None):
		return _denied(doc, "document_changed", new_status="rejected")
	if preview_digest(spec, _row_stamp(tool, spec)) != doc.preview_digest:
		# The human approved another preview than the one the tool gives now. A new proposal
		# and a new approval are needed.
		return _denied(doc, "document_changed", new_status="rejected")
	if needs_second_approval(doc) and doc.status == "pending":
		return _await_second_approval(doc)
	if doc.status == AWAITING:
		doc.second_approver, doc.second_approved_at = user, now_datetime()
	return _execute(doc, tool, arguments)


def _refuse(doc, reason: str, message: str) -> None:
	"""Log a denied approval of another user's proposal and answer 403. Nothing of it is returned."""
	frappe.db.rollback()
	_log("approve", doc, decision="denied", deny_reason=reason)
	access.commit_own_writes()
	raise frappe.PermissionError(message)


def _await_second_approval(doc) -> dict:
	"""Store the owner's first approval of an R3 proposal. Nothing runs now.

	The preview above ran app code. Whatever it wrote is rolled back first, so the commit carries
	only the proposal and its log row. The proposal is read again under its lock.
	"""
	frappe.db.rollback()
	frappe.clear_messages()
	doc = store.load_proposal(doc.name, for_update=True)
	if doc.status != "pending":
		return _denied(doc, "not_pending")
	doc.status, doc.first_approved_at = AWAITING, now_datetime()
	store.save_proposal(doc)
	_log("approve", doc, decision="allowed")
	access.commit_own_writes()
	return {"executed": False, "deny_reason": None, "proposal": public(doc)}


def _execute(doc, tool: registry.AiTool, arguments: dict) -> dict:
	# Before the request the result is written as `unknown` and committed (contract 10, rule 7).
	# Deliberate V-2 exception: if the process dies midway, a trace stays and the proposal
	# cannot be reused.
	doc.status, doc.result, doc.decided_at = "consumed", "unknown", now_datetime()
	store.save_proposal(doc)
	_log("approve", doc, decision="allowed")
	access.commit_own_writes()

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
	from platform_core.ai import revert

	try:
		# The old values are read from the locked record just before the write (AJA-1002).
		captured = revert.capture(tool, prepared) if tool.tool_class != "app" else None
		if tool.tool_class == "app":
			result = tool.handler(tool.prepare(**arguments)) if tool.prepare else tool.handler(**arguments)
		else:
			result = tool.handler(prepared)
		touched = result.get("name") if isinstance(result, dict) else None
		doc.result = "succeeded"
		doc.result_document = str(touched) if touched else doc.target_name
		revert.record_applied(doc, captured)
	except Exception as error:
		return _execution_error(doc, tool, error, result="unknown")

	store.save_proposal(doc)
	_log(
		"execute",
		doc,
		decision="allowed",
		version=store.latest_version(doc.target_doctype, doc.result_document),
	)
	access.commit_own_writes()
	return {"executed": True, "deny_reason": None, "proposal": public(doc)}


def _pre_check(doc, tool: registry.AiTool, arguments: dict) -> Any:
	"""Run the layer's own check before the write boundary. Return what a built-in write step needs.

	A built-in tool checks the previewed version itself, under a row lock. For an app tool that
	declares `versioned`, the layer locks the stored target row and reads its stamp in that same
	locking read, then runs the preview again and compares preview, target, stamp and version. An app tool's own `prepare` is not part of this check. It runs after the boundary.
	"""
	if tool.tool_class != "app":
		extra = {"expected_version": doc.target_modified} if tool.versioned else {}
		return tool.prepare(**arguments, **extra)
	# For a versioned tool the stored target is locked first. The row stamp comes from that same
	# locking read, so a stale snapshot in the tool's own preview cannot hide a changed target.
	# A proposal without a stored target has nothing to lock. The preview below then fails or differs.
	guarded = _guards_row(tool) and doc.target_doctype and doc.target_name
	stamp = store.locked_row_stamp(doc.target_doctype, doc.target_name) if guarded else None
	# Preview again and compare the whole preview, the target and the version with what the
	# human approved.
	spec = _run_preview(tool, arguments)
	changed = preview_digest(spec, stamp) != doc.preview_digest
	if changed or spec["target_version"] != (doc.target_modified or None):
		raise ToolDenied("document_changed", _("The target changed after the preview.", context=CONTEXT))
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
	access.commit_own_writes()
	return {"executed": False, "deny_reason": "execution_failed", "proposal": public(doc)}


def _error_text(tool: registry.AiTool, error: Exception) -> str:
	"""A fixed code that is stored and returned. The text of the error is never stored or returned.

	The text may carry a field value. The server log gets the tool name and the error type.
	"""
	if isinstance(error, ToolDenied):
		return error.code
	if isinstance(error, frappe.PermissionError):
		log_tool_error(tool.name, error)
		return "permission"
	if isinstance(error, frappe.ValidationError):
		log_tool_error(tool.name, error)
		return "validation_error"
	# The traceback names the place of the failure. The error's own text is left out.
	frappe.log_error(
		title=f"AI tool {tool.name} failed during execution",
		message=traceback_without_text(error),
	)
	return "internal_error"


def reject(proposal_id: str) -> dict:
	def run() -> dict:
		doc = _own(proposal_id, for_update=True)
		if doc.status not in OPEN_STATES:
			raise access.WrongState(_("Only a pending proposal can be rejected.", context=CONTEXT))
		doc.status, doc.decided_at = "rejected", now_datetime()
		store.save_proposal(doc)
		_log("reject", doc, decision="allowed")
		return public(doc)

	return access.human_call("reject", "reject_proposal", run, proposal=proposal_id, log_success=False)


def resolve(proposal_id: str, outcome: str) -> dict:
	"""Close a proposal with an unknown result by a human decision. Writes nothing to the target."""

	def run() -> dict:
		if outcome not in ("succeeded", "failed"):
			frappe.throw(_("outcome must be succeeded or failed.", context=CONTEXT), frappe.ValidationError)
		doc = _own(proposal_id, for_update=True)
		if doc.status != "consumed" or doc.result != "unknown":
			raise access.WrongState(
				_("Only a proposal with an unknown result can be resolved.", context=CONTEXT)
			)
		doc.result, doc.decided_at = outcome, now_datetime()
		store.save_proposal(doc)
		_log("resolve", doc, decision="allowed")
		return public(doc)

	return access.human_call("resolve", "resolve_proposal", run, proposal=proposal_id, log_success=False)
