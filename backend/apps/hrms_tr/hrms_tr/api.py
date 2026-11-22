"""HTTP entry point for a manager or HR user."""

import frappe

from hrms_tr import leave
from hrms_tr.leave import LeaveName


@frappe.whitelist(methods=["POST"])
def approve_leave(name: LeaveName) -> dict:
	return leave.approve(name)
