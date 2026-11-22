"""Definition tools: describe the DocType, its fields and the user's permissions."""

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from frappe.model import NO_VALUE_FIELDS
from pydantic import Field

from platform_core.yapay_zeka import fields, policy
from platform_core.yapay_zeka.errors import CONTEXT, ToolDenied
from platform_core.yapay_zeka.tools import envelope

LAYOUT_FIELDTYPES = NO_VALUE_FIELDS - {"Table", "Table MultiSelect"}
# Named here so that a test can lower it for this module.
MAX_RESULT_BYTES = envelope.MAX_RESULT_BYTES
PERMISSION_TYPES = ("read", "write", "create", "delete", "submit", "cancel")


class SearchDoctypesArguments(ToolArguments):
	query: str | None = Field(default=None, min_length=1)
	limit: int = Field(default=50, ge=1, le=100)


class GetDoctypeSchemaArguments(ToolArguments):
	doctype: str = Field(min_length=1)


def search_doctypes(query: str | None = None, limit: int = 50) -> dict:
	"""Returns the DocType names the user can read."""
	needle = (query or "").lower()
	names = sorted(
		name
		for name in frappe.get_user().get_can_read()
		if name not in policy.READ_BLOCKED and needle in name.lower()
	)
	return envelope.stamp({"doctypes": names[:limit]}, "DocType list")


def get_doctype_schema(doctype: str) -> dict:
	"""Builds the field definitions from the DocType definition at run time.

	`frappe.get_meta` also includes "Custom Field" and "Property Setter" changes.
	"""
	meta = fields.get_meta(doctype)
	permissions = {
		# The value is returned for information, not for the permission decision.
		ptype: False if meta.istable else bool(frappe.has_permission(doctype, ptype))
		for ptype in PERMISSION_TYPES
	}
	if doctype in policy.READ_BLOCKED:
		raise ToolDenied(
			"blocked_doctype", _("DocType {0} is closed to AI tools.", context=CONTEXT).format(doctype)
		)
	if not meta.istable and not any(permissions.values()):
		raise ToolDenied(
			"permission", _("You have no permission on DocType {0}.", context=CONTEXT).format(doctype)
		)

	can_read = fields.readable(meta)
	can_write = fields.writable(meta)
	write_closed = doctype in policy.WRITE_BLOCKED or doctype in policy.ADMIN_DOCTYPES
	return envelope.stamp(
		_schema(doctype, meta, permissions, can_read, can_write, write_closed),
		f"DocType definition: {doctype}",
	)


def _schema(doctype: str, meta, permissions: dict, can_read: set, can_write: set, write_closed: bool) -> dict:
	# The field list is the large part of a definition. It is cut at the byte limit.
	described = [
		_field_schema(field, can_read, can_write)
		for field in meta.fields
		if field.fieldtype not in LAYOUT_FIELDTYPES
	]
	fields, cut = envelope.fit_rows(described, MAX_RESULT_BYTES)
	return {
		"doctype": doctype,
		"description": meta.description,
		"module": meta.module,
		"is_submittable": bool(meta.is_submittable),
		"is_single": bool(meta.issingle),
		"is_child_table": bool(meta.istable),
		"title_field": meta.title_field,
		"generic_write_tools": "closed" if write_closed else "open",
		"permissions": permissions,
		"fields": fields,
		"truncated": cut,
	}


def _field_schema(field, can_read: set[str], can_write: set[str]) -> dict:
	secret = policy.is_secret_field(field)
	result = {
		"fieldname": field.fieldname,
		"fieldtype": field.fieldtype,
		"label": field.label,
		"description": field.description,
		"options": field.options,
		"reqd": bool(field.reqd),
		"read_only": bool(field.read_only),
		"permlevel": field.permlevel or 0,
		"secret": secret,
		"readable": field.fieldname in can_read,
		"writable": field.fieldname in can_write and not field.read_only,
	}
	return {key: value for key, value in result.items() if value is not None}
