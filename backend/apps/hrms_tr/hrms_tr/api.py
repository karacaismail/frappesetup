"""HTTP entry point for a manager or HR user."""

import frappe

from hrms_tr import leave
from hrms_tr.leave import LeaveName


# leave.approve locks the target and checks its read, write, and submit rights.
@frappe.whitelist(methods=["POST"])  # nosemgrep: backend.dev.guvenlik.fixtures.frappe-missing-permission
def approve_leave(name: LeaveName) -> dict:
	return leave.approve(name)
