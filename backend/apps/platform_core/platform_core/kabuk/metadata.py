"""Effective metadata for the current tenant user."""

import frappe
from frappe.model import NO_VALUE_FIELDS
from frappe.permissions import has_permission, is_system_user

from platform_core.kabuk.cache import permission_version
from platform_core.kabuk.catalog import CATALOG_VERSION, FIELD_COMPONENTS
from platform_core.kabuk.metadata_policy import MetadataPolicy, load_metadata_policy, verified_mobile_request
from platform_core.kabuk.serialization import digest, project_meta

TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}


def get_doctype(doctype: str, user: str, *, surface: str = "web") -> dict:
	"""Authorize the current user before returning the parent and visible child schemas."""
	if not user or user == "Guest" or user != frappe.session.user:
		frappe.throw(
			frappe._("You cannot read this DocType.", context="shell.metadata"), frappe.PermissionError
		)
	if not isinstance(doctype, str) or not doctype.strip() or len(doctype) > 140:
		frappe.throw(
			frappe._("A valid DocType name is required.", context="shell.metadata"), frappe.ValidationError
		)
	if surface not in {"web", "mobile"}:
		frappe.throw(
			frappe._("A valid metadata surface is required.", context="shell.metadata"),
			frappe.ValidationError,
		)

	mobile = verified_mobile_request(user)
	mobile_requested = surface == "mobile" or getattr(frappe.local, "mobile_identity", None) is not None
	limited = mobile or not is_system_user(user)
	policy = load_metadata_policy()
	canonical_name = frappe.db.exists("DocType", doctype, cache=True)
	meta = frappe.get_meta(canonical_name) if canonical_name else None
	if (
		meta is None
		or meta.istable
		or not has_permission(meta.name, "read", user=user, print_logs=False)
		or (mobile_requested and not mobile)
		or (limited and policy.errors)
		or (mobile and not policy.allows_mobile(meta.name))
	):
		message = frappe._("You cannot read this DocType.", context="shell.metadata")
		frappe.msgprint(message, indicator="red")
		raise frappe.PermissionError(message)

	raw = meta.as_dict()
	schema = visible_schema(meta, raw, user, policy, limited=limited, mobile=mobile)
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
				child,
				child_raw,
				user,
				policy,
				parenttype=meta.name,
				parent_readable=parent_readable,
				limited=limited,
				mobile=mobile,
			)

	projection = {"schema": schema, "child_tables": child_tables}
	return {
		**projection,
		"meta_hash": digest(projection),
		"catalog_version": CATALOG_VERSION,
		"mobile_cache_allowed": mobile,
		"perm_version": digest([permission_version(), sorted(frappe.get_roles(user))]),
	}


def visible_schema(
	meta,
	raw: dict,
	user: str,
	policy: MetadataPolicy,
	*,
	parenttype: str | None = None,
	parent_readable: set[str] | None = None,
	limited: bool = True,
	mobile: bool = False,
) -> dict:
	readable = permitted_fields(meta, user, "read", parenttype=parenttype)
	writable = permitted_fields(meta, user, "write", parenttype=parenttype)
	restricted_doctype = meta.name in policy.restricted_doctypes
	masked = {item.fieldname for item in meta.fields if item.get("mask")}
	writable -= masked
	restricted = {
		field.fieldname
		for field in meta.fields
		if restricted_doctype or field.fieldtype == "Password" or int(field.permlevel or 0) > 0
	}
	restricted |= masked | policy.restricted_fields.get(meta.name, set())
	if limited:
		readable -= restricted
	if mobile:
		readable -= {
			field.fieldname
			for field in meta.fields
			if field.fieldtype in TABLE_FIELD_TYPES and not policy.allows_mobile(field.options)
		}
	schema = project_meta(raw, readable, writable, parent_readable=parent_readable)
	schema["sensitivity"] = "restricted" if restricted_doctype else "standard"
	for field in schema["fields"]:
		field["component"] = FIELD_COMPONENTS.get(field["fieldtype"])
		field["sensitivity"] = "restricted" if field["fieldname"] in restricted else "standard"
		for key in ("label", "description"):
			if field.get(key):
				field[key] = frappe._(field[key], context=meta.name)
		options = field.get("options")
		if field["fieldtype"] == "Select" and isinstance(options, str):
			field["choices"] = [
				{"value": option, "label": frappe._(option, context=meta.name)}
				for option in options.split("\n")
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
