"""Effective metadata for the current tenant user."""

import frappe
from frappe.model import NO_VALUE_FIELDS
from frappe.permissions import has_permission

from platform_core.kabuk.cache import permission_version
from platform_core.kabuk.catalog import CATALOG_VERSION, FIELD_COMPONENTS
from platform_core.kabuk.serialization import digest, project_meta

TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}


def get_doctype(doctype: str, user: str, *, surface: str = "web") -> dict:
	"""Authorize the current user before returning the parent and visible child schemas."""
	if not user or user == "Guest" or user != frappe.session.user:
		frappe.throw(frappe._("You cannot read this DocType."), frappe.PermissionError)
	if not isinstance(doctype, str) or not doctype.strip() or len(doctype) > 140:
		frappe.throw(frappe._("A valid DocType name is required."), frappe.ValidationError)
	if surface not in {"web", "mobile"}:
		frappe.throw(frappe._("A valid metadata surface is required."), frappe.ValidationError)

	# The identity hook establishes this context after verifying a mobile token.
	mobile = surface == "mobile" or getattr(frappe.local, "mobile_identity", None) is not None
	canonical_name = frappe.db.exists("DocType", doctype, cache=True)
	meta = frappe.get_meta(canonical_name) if canonical_name else None
	if (
		meta is None
		or meta.istable
		or not has_permission(meta.name, "read", user=user, print_logs=False)
		or (mobile and not mobile_allows(meta.name))
	):
		message = frappe._("You cannot read this DocType.")
		frappe.msgprint(message, indicator="red")
		raise frappe.PermissionError(message)

	raw = meta.as_dict()
	schema = visible_schema(meta, raw, user, mobile=mobile)
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
				child, child_raw, user, parenttype=meta.name, parent_readable=parent_readable, mobile=mobile
			)

	projection = {"schema": schema, "child_tables": child_tables}
	return {
		**projection,
		"meta_hash": digest(projection),
		"catalog_version": CATALOG_VERSION,
		"perm_version": digest([permission_version(), sorted(frappe.get_roles(user))]),
	}


def configured_doctypes(key: str) -> set[str]:
	values = frappe.conf.get(key)
	return {value for value in values if isinstance(value, str)} if isinstance(values, list) else set()


def mobile_allows(doctype: str) -> bool:
	return doctype in configured_doctypes("shell_mobile_doctypes") and doctype not in configured_doctypes(
		"shell_restricted_doctypes"
	)


def visible_schema(
	meta,
	raw: dict,
	user: str,
	*,
	parenttype: str | None = None,
	parent_readable: set[str] | None = None,
	mobile: bool = False,
) -> dict:
	readable = permitted_fields(meta, user, "read", parenttype=parenttype)
	writable = permitted_fields(meta, user, "write", parenttype=parenttype)
	restricted_doctype = meta.name in configured_doctypes("shell_restricted_doctypes")
	restricted = {
		field.fieldname
		for field in meta.fields
		if restricted_doctype or field.fieldtype == "Password" or int(field.permlevel or 0) > 0
	}
	if mobile:
		readable -= restricted
		readable -= {
			field.fieldname
			for field in meta.fields
			if field.fieldtype in TABLE_FIELD_TYPES and not mobile_allows(field.options)
		}
	schema = project_meta(raw, readable, writable, parent_readable=parent_readable)
	schema["sensitivity"] = "restricted" if restricted_doctype else "standard"
	for field in schema["fields"]:
		field["component"] = FIELD_COMPONENTS.get(field["fieldtype"])
		field["sensitivity"] = "restricted" if field["fieldname"] in restricted else "standard"
		for key in ("label", "description"):
			if field.get(key):
				field[key] = frappe._(field[key])
		options = field.get("options")
		if field["fieldtype"] == "Select" and isinstance(options, str):
			field["choices"] = [
				{"value": option, "label": frappe._(option)} for option in options.split("\n")
			]
		if field["component"] is None:
			field.pop("options", None)
			field.pop("default", None)
	return schema


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
