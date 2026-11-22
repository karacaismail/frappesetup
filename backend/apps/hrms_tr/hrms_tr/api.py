"""HTTP entry point for a manager or HR user."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from hrms_tr import leave
from hrms_tr.leave import LeaveName, LeaveVersion


# leave.approve locks the target and checks its read, write, and submit rights.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
@rate_limit(limit=60, seconds=60, methods=["POST"], ip_based=False, user_based=True)
def approve_leave(name: LeaveName, version: LeaveVersion | None = None) -> dict[str, str]:
	if version is None:
		frappe.throw(_("Read the leave application version before approving."), frappe.ValidationError)
	return leave.approve(name, expected_version=version)
