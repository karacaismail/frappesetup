"""Keep Leave Application access scoped when platform rules are missing."""

import frappe
from frappe import _

DOCTYPE = "Leave Application"
RULE_DOCTYPE = "Access Rule"
ENGINE_HOOKS = {
	"permission_query_conditions": "platform_core.erisim.hooks.query_conditions",
	"has_permission": "platform_core.erisim.hooks.has_permission",
}


def engine_available():
	for hook, path in ENGINE_HOOKS.items():
		if path not in frappe.get_hooks(hook, {}).get("*", []):
			return False
		try:
			if not callable(frappe.get_attr(path)):
				return False
		except (ImportError, AttributeError, frappe.ValidationError):
			return False
	return True


def rules_active():
	active = getattr(frappe.local, "hrms_tr_access_rules_active", None)
	if active is None:
		active = (
			engine_available()
			and bool(frappe.db.exists("DocType", RULE_DOCTYPE))
			and bool(frappe.db.exists(RULE_DOCTYPE, {"document_type": DOCTYPE, "is_active": 1}))
		)
		frappe.local.hrms_tr_access_rules_active = active
	return active


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
