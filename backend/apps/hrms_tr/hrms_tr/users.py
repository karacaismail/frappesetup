"""Keep HRMS TR tenant users on the website login path."""

import frappe
from frappe import _

EMPLOYEE_ROLE = "HRMS TR Employee"
APPROVER_PROFILES = ("HRMS TR Manager", "HRMS TR Admin")
HRMS_TR_ROLES = (EMPLOYEE_ROLE, *APPROVER_PROFILES)
NATIVE_LEAVE_APPROVER = "Leave Approver"


def keep_portal_user(doc, method=None):
	if doc.name == "Administrator" or not any(row.role in HRMS_TR_ROLES for row in doc.roles):
		return
	# HRMS adds Leave Approver during User.validate and when Employee.leave_approver is set.
	# HRMS TR's own role grants approval without granting Desk access.
	doc.roles[:] = [row for row in doc.roles if row.role != NATIVE_LEAVE_APPROVER]
	if doc.has_desk_access():
		frappe.throw(_("HRMS TR users cannot be assigned Desk roles."), frappe.PermissionError)
	doc.user_type = "Website User"
