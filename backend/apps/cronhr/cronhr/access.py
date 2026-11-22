"""Keep Leave Application access scoped when platform rules are missing."""

import frappe
from frappe import _

DOCTYPE = "Leave Application"


def rules_active():
	return frappe.db.exists("Access Rule", {"document_type": DOCTYPE, "is_active": 1})


def query_condition(user=None, doctype=None):
	if (user or frappe.session.user) != "Administrator" and not rules_active():
		return frappe.qb.DocType(DOCTYPE).name.isnull()
	return None


def has_permission(doc, ptype=None, user=None, debug=False):
	return (user or frappe.session.user) == "Administrator" or bool(rules_active())


def deny_sharing(doc, method=None):
	# Frappe shares are added to the results after the normal row permission check.
	if doc.share_doctype == DOCTYPE:
		frappe.throw(_("Leave applications cannot be shared."), frappe.PermissionError)
