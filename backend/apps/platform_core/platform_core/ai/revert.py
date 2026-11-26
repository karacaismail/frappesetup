"""Revert of an applied proposal (AJA-1002). Decision note: `docs/decisions/0002-ai-layer.md`, section 7.

The layer never writes a revert itself. When an update succeeds, the old values of the fields it
changed are stored on the proposal. The `propose_revert` endpoint opens a new pending proposal
from those values. That proposal goes through the same approval as any other.
"""

import json
from typing import Any

import frappe
from frappe.model import table_fields

from platform_core.ai import access, fields, proposals, registry, store
from platform_core.ai.errors import ToolDenied

# Only a field update can be undone by writing old values back. A create, a delete, a submit or
# an admin change has no old field values to write.
REVERTABLE_TOOLS = frozenset({"plt_update_document"})


def capture(tool: registry.AiTool, prepared: Any) -> dict | None:
	"""Read the old values just before the write. `prepared` is the locked record and the input.

	Only fields the user may read are kept. A revert preview shows the old value as its new
	value, so an unreadable field would leak through it. Such an update gets no revert values.
	A child table is replaced as a whole and its rows carry their own names, so an update of a
	table gets none either.
	"""
	if tool.name not in REVERTABLE_TOOLS:
		return None
	doc, data = prepared
	readable = fields.readable(doc.meta)
	if any(key not in readable or doc.meta.get_field(key).fieldtype in table_fields for key in data):
		return None
	return {key: doc.get(key) for key in data}


def record_applied(doc, captured: dict | None) -> None:
	"""Store, on the applied proposal, the old values of the fields that changed and the new version."""
	if captured is None or not doc.target_doctype or not doc.target_name:
		return
	target = frappe.get_doc(doc.target_doctype, doc.target_name)
	changed = {
		key: old
		for key, old in captured.items()
		if proposals.canonical(old) != proposals.canonical(target.get(key))
	}
	if not changed:
		return
	doc.revert_json = proposals.canonical(changed)
	doc.applied_version = store.row_stamp(doc.target_doctype, doc.target_name)


def _refusal(source) -> str | None:
	if source.status != "consumed" or source.result != "succeeded":
		return "not_applied"
	if source.tool not in REVERTABLE_TOOLS or not source.revert_json or not source.applied_version:
		return "not_revertable"
	if store.row_stamp(source.target_doctype, source.target_name) != source.applied_version:
		return "record_changed"
	return None


def _refused(source, code: str) -> dict:
	access.record_denial(
		"revert",
		code,
		tool="propose_revert",
		target_doctype=source.target_doctype,
		target_name=source.target_name,
		proposal=source.name,
	)
	return {"opened": False, "deny_reason": code, "proposal": None}


def propose(proposal_id: str) -> dict:
	"""The `propose_revert` endpoint. Opens a pending revert proposal. Writes nothing to the record."""

	def run() -> dict:
		source = proposals.own(proposal_id)
		code = _refusal(source)
		if code:
			return _refused(source, code)
		tool = registry.find(source.tool)
		if tool is None or not tool.visible():
			return _refused(source, "role_required")
		arguments = {
			"doctype": source.target_doctype,
			"name": source.target_name,
			"data": json.loads(source.revert_json),
		}
		try:
			_result, doc = proposals.open_proposal(tool, arguments, source=source)
		except ToolDenied as error:
			return _refused(source, error.code)
		except frappe.DoesNotExistError:
			return _refused(source, "record_changed")
		except frappe.PermissionError:
			return _refused(source, "permission")
		except frappe.ValidationError:
			return _refused(source, "invalid_arguments")
		if doc.target_modified != source.applied_version:
			# The record changed between the check above and the preview.
			return _refused(source, "record_changed")
		access.record(
			"revert",
			decision="allowed",
			tool=doc.tool,
			tool_class=doc.tool_class,
			target_doctype=doc.target_doctype,
			target_name=doc.target_name,
			proposal=doc.name,
			approval_state=doc.status,
		)
		return {"opened": True, "deny_reason": None, "proposal": proposals.public(doc)}

	return access.human_call("revert", "propose_revert", run, proposal=proposal_id, log_success=False)
