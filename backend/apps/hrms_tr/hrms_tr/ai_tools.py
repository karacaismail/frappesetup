"""Register a proposal-only operation with the platform AI layer."""

from frappe import _
from pydantic import BaseModel, ConfigDict, Field

from hrms_tr import leave
from hrms_tr.leave import LeaveName


class ApprovalArguments(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: LeaveName = Field(description="Document name of the leave application.")
	version: str = Field(min_length=1, max_length=40, description="Modified value of the reviewed draft.")


def declarations() -> list[dict]:
	return [
		{
			"name": "approve_leave",
			"description": "Propose approving and submitting an open leave application.",
			"arguments": "hrms_tr.ai_tools.ApprovalArguments",
			"kind": "write",
			"destructive": True,
			"roles": list(leave.APPROVER_ROLES),
			"handler": "hrms_tr.ai_tools.execute_approval",
			"preview": "hrms_tr.ai_tools.preview_approval",
		}
	]


def preview_approval(name: str, version: str) -> dict:
	doc = leave.pending_leave(name, expected_version=version)
	return {
		"summary": _("Approve and submit leave application {0}.").format(doc.name),
		"target_doctype": doc.doctype,
		"target_name": doc.name,
		"target_version": str(doc.modified),
		"changes": [
			{"field": "status", "before": "Open", "after": "Approved"},
			{"field": "docstatus", "before": 0, "after": 1},
		],
		"details": {
			"name": doc.name,
			"employee_name": doc.employee_name,
			"from_date": str(doc.from_date),
			"to_date": str(doc.to_date),
			"total_leave_days": doc.total_leave_days,
		},
	}


def execute_approval(name: str, version: str) -> dict:
	return leave.approve(name, expected_version=version)
