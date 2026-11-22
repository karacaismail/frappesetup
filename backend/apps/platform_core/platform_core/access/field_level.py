"""Field level management. Sets the permission level of Frappe with built-in functions (decision note, section 8)."""

import frappe
from frappe import _
from frappe.core.doctype.custom_docperm.custom_docperm import update_custom_docperm
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.custom.doctype.property_setter.property_setter import delete_property_setter, make_property_setter
from frappe.permissions import add_permission, setup_custom_perms
from frappe.utils import cint

from platform_core.access.rules import PROTECTED_DOCTYPES

MAX_LEVEL = 9


def _require_admin(doctype: str) -> None:
	frappe.only_for("System Manager")
	if not frappe.db.exists("DocType", doctype, cache=True):
		frappe.throw(_("Document type {0} not found.").format(doctype), frappe.DoesNotExistError)
	if doctype in PROTECTED_DOCTYPES:
		# Closing a field in these document types can lock permission management.
		frappe.throw(_("Field levels of {0} cannot be changed here.").format(frappe.bold(doctype)))


def set_field_level(doctype: str, fieldname: str, permlevel: int) -> dict:
	_require_admin(doctype)
	if not 0 <= permlevel <= MAX_LEVEL:
		frappe.throw(_("Permission level must be between 0 and {0}.").format(MAX_LEVEL))
	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df:
		frappe.throw(_("{0} is not a field of {1}.").format(frappe.bold(fieldname), doctype))
	previous = cint(df.permlevel)
	if previous != permlevel:
		delete_property_setter(doctype, property="permlevel", field_name=fieldname)
		frappe.clear_cache(doctype=doctype)
		if cint(frappe.get_meta(doctype).get_field(fieldname).permlevel) != permlevel:
			# The authority was checked above with `only_for`. This function does not check permissions.
			make_property_setter(doctype, fieldname, "permlevel", permlevel, "Int")
		frappe.clear_cache(doctype=doctype)
	return {
		"doctype": doctype,
		"fieldname": fieldname,
		"permlevel": permlevel,
		"previous_permlevel": previous,
	}


def set_level_access(doctype: str, role: str, permlevel: int, read: bool, write: bool) -> dict:
	_require_admin(doctype)
	if not 1 <= permlevel <= MAX_LEVEL:
		frappe.throw(_("Permission level must be between 1 and {0}.").format(MAX_LEVEL))
	if write and not read:
		frappe.throw(_("Write access needs read access."))
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} not found.").format(role), frappe.DoesNotExistError)

	# On the first change Frappe copies the role permissions to the “Custom DocPerm” table.
	setup_custom_perms(doctype)
	filters = {"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0}
	existing = frappe.db.get_value("Custom DocPerm", filters)
	if not read:
		if existing:
			# `force` skips the search for records that link to this row. Nothing links to a
			# permission row, and that search took most of the request (measured for O-31).
			# Frappe's own permission manager removes the row the same way
			# (`frappe/core/page/permission_manager/permission_manager.py:170`).
			frappe.delete_doc("Custom DocPerm", existing, force=True)
	else:
		if not existing:
			existing = add_permission(doctype, role, permlevel, "read")
		# The row is updated by name. A search by role and level can also find the `if_owner` row.
		update_custom_docperm(existing, {"read": 1, "write": cint(write)})
		validate_permissions_for_doctype(doctype)
	frappe.clear_cache(doctype=doctype)
	return {
		"doctype": doctype,
		"role": role,
		"permlevel": permlevel,
		"read": bool(read),
		"write": bool(write),
	}
