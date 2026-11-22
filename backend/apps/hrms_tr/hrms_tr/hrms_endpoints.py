"""Close legacy HRMS RPC routes that do not enforce HRMS TR leave access."""

import frappe
from frappe import _


@frappe.whitelist()
def deny_legacy_leave_query():
	frappe.throw(_("Read leave information through an authorized leave application."), frappe.PermissionError)
