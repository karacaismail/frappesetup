"""Register a proposal-only operation with the platform AI layer."""

from pydantic import BaseModel, ConfigDict, Field

from cronhr import leave
from cronhr.leave import LeaveName


class ApprovalArguments(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: LeaveName
	version: str = Field(min_length=1, max_length=40, description="Modified value of the reviewed draft.")


def declarations() -> list[dict]:
	return [
		{
			"name": "approve_leave",
			"description": "Propose approving and submitting an open leave application.",
			"arguments": "cronhr.ai_tools.ApprovalArguments",
			"kind": "write",
			"roles": list(leave.APPROVER_ROLES),
			"handler": "cronhr.ai_tools.execute_approval",
			"preview": "cronhr.ai_tools.preview_approval",
		}
	]


def preview_approval(name: str, version: str) -> dict:
	doc = leave.pending_leave(name, expected_version=version)
	return {
		"summary": f"Approve and submit leave application {doc.name}.",
		"target_doctype": doc.doctype,
		"target_name": doc.name,
		"target_version": str(doc.modified),
		"changes": {
			"status": {"before": "Open", "after": "Approved"},
			"docstatus": {"before": 0, "after": 1},
		},
	}


def execute_approval(name: str, version: str) -> dict:
	return leave.approve(name, expected_version=version)
