"""Tanım araçları: DocType'ı, alanlarını ve kullanıcının izinlerini anlatır."""

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from frappe.model import NO_VALUE_FIELDS
from pydantic import Field

from platform_core.yapay_zeka import fields, policy
from platform_core.yapay_zeka.errors import ToolDenied

LAYOUT_FIELDTYPES = NO_VALUE_FIELDS - {"Table", "Table MultiSelect"}
PERMISSION_TYPES = ("read", "write", "create", "delete", "submit", "cancel")


class SearchDoctypesArguments(ToolArguments):
	query: str | None = Field(default=None, min_length=1)
	limit: int = Field(default=50, ge=1, le=100)


class GetDoctypeSchemaArguments(ToolArguments):
	doctype: str = Field(min_length=1)


def search_doctypes(query: str | None = None, limit: int = 50) -> dict:
	"""Kullanıcının okuyabildiği DocType adlarını döner."""
	needle = (query or "").lower()
	names = sorted(
		name
		for name in frappe.get_user().get_can_read()
		if name not in policy.READ_BLOCKED and needle in name.lower()
	)
	return {"doctypes": names[:limit]}


def get_doctype_schema(doctype: str) -> dict:
	"""Alan tanımlarını çalışma anında DocType tanımından üretir.

	`frappe.get_meta` “Custom Field” ve “Property Setter” değişikliklerini de içerir.
	"""
	meta = fields.get_meta(doctype)
	permissions = {
		# Değer izin kararı için değil, bilgi için döner.
		ptype: False if meta.istable else bool(frappe.has_permission(doctype, ptype))
		for ptype in PERMISSION_TYPES
	}
	if doctype in policy.READ_BLOCKED:
		raise ToolDenied("blocked_doctype", _("DocType {0} is closed to AI tools.").format(doctype))
	if not meta.istable and not any(permissions.values()):
		raise ToolDenied("permission", _("You have no permission on DocType {0}.").format(doctype))

	can_read = fields.readable(meta)
	can_write = fields.writable(meta)
	write_closed = doctype in policy.WRITE_BLOCKED or doctype in policy.ADMIN_DOCTYPES
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
		"fields": [
			_field_schema(field, can_read, can_write)
			for field in meta.fields
			if field.fieldtype not in LAYOUT_FIELDTYPES
		],
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
