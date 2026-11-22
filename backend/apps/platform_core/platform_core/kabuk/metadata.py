"""Effective metadata for the current tenant user."""

import frappe
from frappe.model import NO_VALUE_FIELDS
from frappe.permissions import has_permission

from platform_core.kabuk.cache import permission_version
from platform_core.kabuk.serialization import digest, project_meta

TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}


def get_doctype(doctype: str, user: str) -> dict:
	"""Authorize the current user before returning the parent and visible child schemas."""
	if not user or user == "Guest" or user != frappe.session.user:
		frappe.throw(frappe._("You cannot read this DocType."), frappe.PermissionError)
	if not isinstance(doctype, str) or not doctype.strip() or len(doctype) > 140:
		frappe.throw(frappe._("A valid DocType name is required."), frappe.ValidationError)

	canonical_name = frappe.db.exists("DocType", doctype, cache=True)
	meta = frappe.get_meta(canonical_name) if canonical_name else None
	if meta is None or meta.istable or not has_permission(meta.name, "read", user=user, print_logs=False):
		message = frappe._("You cannot read this DocType.")
		frappe.msgprint(message, indicator="red")
		raise frappe.PermissionError(message)

	raw = meta.as_dict()
	schema = visible_schema(meta, raw, user)
	parent_readable = {field["fieldname"] for field in schema["fields"]}
	child_tables = {}
	for field in schema["fields"]:
		child_name = field.get("options")
		if field["fieldtype"] not in TABLE_FIELD_TYPES or not child_name or child_name in child_tables:
			continue
		child = frappe.get_meta(child_name)
		if child.istable:
			child_raw = child.as_dict()
			child_tables[child.name] = visible_schema(
				child, child_raw, user, parenttype=meta.name, parent_readable=parent_readable
			)

	projection = {"schema": schema, "child_tables": child_tables}
	return {
		**projection,
		"meta_hash": digest(projection),
		"perm_version": digest([permission_version(), sorted(frappe.get_roles(user))]),
	}


def visible_schema(
	meta, raw: dict, user: str, *, parenttype: str | None = None, parent_readable: set[str] | None = None
) -> dict:
	readable = permitted_fields(meta, user, "read", parenttype=parenttype)
	writable = permitted_fields(meta, user, "write", parenttype=parenttype)
	return project_meta(raw, readable, writable, parent_readable=parent_readable)


def permitted_fields(meta, user: str, permission_type: str, *, parenttype: str | None = None) -> set[str]:
	"""Include structural fields at the levels Frappe permits."""
	if user == "Administrator":
		return {field.fieldname for field in meta.fields}
	names = set(
		meta.get_permitted_fieldnames(parenttype=parenttype, user=user, permission_type=permission_type)
	)
	levels = set(meta.get_permlevel_access(permission_type=permission_type, parenttype=parenttype, user=user))
	if permission_type == "read":
		levels.update(int(field.permlevel or 0) for field in meta.fields if field.fieldname in names)
	names.update(
		field.fieldname
		for field in meta.fields
		if field.fieldtype in NO_VALUE_FIELDS and int(field.permlevel or 0) in levels
	)
	return names
