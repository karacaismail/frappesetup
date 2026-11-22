"""Effective metadata for the authenticated tenant user."""

import frappe
from frappe.model import NO_VALUE_FIELDS

from platform_core.kabuk.cache import CACHE_SECONDS, permission_version
from platform_core.kabuk.http import conditional_response
from platform_core.kabuk.serialization import digest, project_meta


def get_doctype(doctype: str, user: str) -> dict | None:
	"""Project metadata after the HTTP entry point authorizes the current user."""
	meta = frappe.get_meta(doctype)

	readable = permitted_fields(meta, user, "read")
	writable = permitted_fields(meta, user, "write")
	raw = meta.as_dict()
	meta_hash = digest(raw)
	# Native get_meta already caches the site schema. The immutable projection is
	# additionally addressed by its content hash, independent from user permissions.
	schema_key = f"platform_core:kabuk:schema:{meta_hash}"
	schema = frappe.cache.get_value(schema_key)
	if schema is None:
		all_names = {field.fieldname for field in meta.fields}
		schema = project_meta(raw, all_names, all_names)
		frappe.cache.set_value(schema_key, schema, expires_in_sec=CACHE_SECONDS)

	version = digest(
		[
			permission_version(),
			sorted(frappe.get_roles(user)),
			sorted(readable),
			sorted(writable),
		]
	)
	key = f"platform_core:kabuk:effective:{digest([user, version, meta_hash])}"
	payload = frappe.cache.get_value(key)
	if payload is None:
		payload = {
			"schema": project_meta(schema, readable, writable),
			"meta_hash": meta_hash,
			"perm_version": version,
		}
		frappe.cache.set_value(key, payload, expires_in_sec=CACHE_SECONDS)
	return conditional_response(payload, user, version)


def permitted_fields(meta, user: str, permission_type: str) -> set[str]:
	"""Frappe excludes layout and table fields from get_permitted_fieldnames."""
	if user == "Administrator":
		return {field.fieldname for field in meta.fields}
	names = set(meta.get_permitted_fieldnames(user=user, permission_type=permission_type))
	levels = set(meta.get_permlevel_access(permission_type=permission_type, user=user))
	names.update(
		field.fieldname
		for field in meta.fields
		if field.fieldtype in NO_VALUE_FIELDS and int(field.permlevel or 0) in levels
	)
	return names
