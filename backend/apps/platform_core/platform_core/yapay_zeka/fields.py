"""Work out which fields the user may read and write, and clean the response."""

from typing import TYPE_CHECKING, Any

import frappe
from frappe import _

from platform_core.yapay_zeka import policy
from platform_core.yapay_zeka.errors import CONTEXT, ToolDenied

if TYPE_CHECKING:
	from frappe.model.meta import Meta

STANDARD_FIELDS = ("name", "owner", "creation", "modified", "modified_by", "docstatus", "idx")


def get_meta(doctype: str) -> "Meta":
	try:
		return frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		frappe.clear_messages()
		raise ToolDenied(
			"unknown_doctype", _("DocType {0} does not exist.", context=CONTEXT).format(doctype)
		) from None


def _permitted(meta: "Meta", ptype: str, parenttype: str | None) -> set[str]:
	"""Permitted field names. A child table field is also included by its permission level.

	Frappe's `get_permitted_fieldnames` function does not count table fields. A table field is
	permitted when its permission level is open to the user.
	"""
	names = set(meta.get_permitted_fieldnames(parenttype=parenttype, permission_type=ptype))
	if not meta.istable:
		levels = set(meta.get_permlevel_access(permission_type=ptype))
		names |= {field.fieldname for field in meta.get_table_fields() if (field.permlevel or 0) in levels}
	return names


def readable(meta: "Meta", parenttype: str | None = None) -> set[str]:
	"""Fields the user can read that are not secret."""
	permitted = _permitted(meta, "read", parenttype)
	names = {
		field.fieldname
		for field in meta.fields
		if field.fieldname in permitted and not policy.is_secret_field(field)
	}
	return names | set(STANDARD_FIELDS)


def writable(meta: "Meta", parenttype: str | None = None) -> set[str]:
	"""Fields the user can write that are not secret."""
	permitted = _permitted(meta, "write", parenttype)
	return {
		field.fieldname
		for field in meta.fields
		if field.fieldname in permitted and not policy.is_secret_field(field)
	}


def check_readable(meta: "Meta", fieldname: str) -> None:
	"""Refuse the call if the field cannot be read. Filter and sort fields pass through here too."""
	if fieldname in STANDARD_FIELDS:
		return
	field = meta.get_field(fieldname)
	if field is None or not fieldname.isidentifier():
		raise ToolDenied("invalid_arguments", _("Unknown field: {0}", context=CONTEXT).format(fieldname))
	if policy.is_secret_field(field):
		raise ToolDenied("secret_field", _("Field {0} is secret.", context=CONTEXT).format(fieldname))
	if fieldname not in readable(meta):
		raise ToolDenied(
			"field_not_permitted", _("You may not read field {0}.", context=CONTEXT).format(fieldname)
		)


def clean(data: dict[str, Any], meta: "Meta", parenttype: str | None = None) -> dict[str, Any]:
	"""Keep only the readable fields in a record dict. Child tables are cleaned too.

	Frappe empties the value of a field with a high permission level but leaves the key.
	Here the key is removed too. Secret fields and internal keys are removed too.
	"""
	allowed = readable(meta, parenttype)
	result = {}
	for key, value in data.items():
		field = meta.get_field(key)
		if key.startswith("_") or policy.is_secret_fieldname(key):
			continue
		if field is not None and key not in allowed:
			continue
		if (
			field is not None
			and field.fieldtype in ("Table", "Table MultiSelect")
			and isinstance(value, list)
		):
			if field.options in policy.READ_BLOCKED:
				continue
			child_meta = frappe.get_meta(field.options)
			value = [clean(row, child_meta, meta.name) if isinstance(row, dict) else row for row in value]
		result[key] = value
	return result
