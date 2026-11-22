"""HTTP entry point for a manager or HR user."""

import frappe

from cronhr import leave
from cronhr.leave import LeaveName


@frappe.whitelist(methods=["POST"])
def approve_leave(name: LeaveName) -> dict:
	return leave.approve(name)
