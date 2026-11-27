"""Register a proposal-only operation with the platform AI layer."""

import frappe
from frappe import _
from pydantic import BaseModel, ConfigDict, Field

from hrms_tr import leave
from hrms_tr.leave import LeaveName


class ApprovalArguments(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: LeaveName = Field(description="Document name of the leave application.")


def declarations() -> list[dict]:
	"""Register the leave approval tool with a preview and required human approval."""
	return [
		{
			"name": "approve_leave",
			"description": "Propose approving and submitting an open leave application.",
			"arguments": "hrms_tr.ai_tools.ApprovalArguments",
			"kind": "write",
			"destructive": True,
			"versioned": True,
			"roles": list(leave.TOOL_APPROVER_ROLES),
			"handler": "hrms_tr.ai_tools.execute_approval",
			"preview": "hrms_tr.ai_tools.preview_approval",
		}
	]


def preview_approval(name: str) -> dict:
	doc = leave.pending_leave(name)
	return {
		"summary": _("Approve and submit leave application {0}.", context="hrms_tr").format(doc.name),
		"target_doctype": doc.doctype,
		"target_name": doc.name,
		"target_version": str(doc.modified),
		"changes": [
			{
				"fieldname": "status",
				"label": _("Status", context="hrms_tr"),
				"old": doc.status,
				"new": "Approved",
			},
			{
				"fieldname": "docstatus",
				"label": _("Document Status", context="hrms_tr"),
				"old": int(doc.docstatus),
				"new": 1,
			},
		],
		"details": {"name": doc.name},
	}


def execute_approval(name: str) -> dict[str, str]:
	try:
		return leave.approve(name)
	except (frappe.ValidationError, frappe.PermissionError):
		# The platform stores this exception in the proposal. HRMS errors may contain personal data.
		frappe.clear_messages()
		raise frappe.ValidationError(
			_("The leave application could not be approved.", context="hrms_tr")
		) from None
