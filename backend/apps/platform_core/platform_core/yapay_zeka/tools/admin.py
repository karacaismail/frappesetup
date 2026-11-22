"""Admin tools: custom field, field property, role and permission changes.

Open only to the "System Manager" role. Each tool produces a preview and asks for human approval.
Execution uses Frappe's own admin paths. These paths check the authorization again.
"""

import json
from typing import Literal

import frappe
from frappe import _
from frappe.core.page.permission_manager import permission_manager
from frappe.mcp.tools import ToolArguments
from pydantic import Field

from platform_core.yapay_zeka import fields, policy, retention, store, versioning
from platform_core.yapay_zeka.errors import CONTEXT, ToolDenied

ADMIN_ROLE = "System Manager"

FieldType = Literal[
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Check",
	"Date",
	"Datetime",
	"Time",
	"Select",
	"Link",
	"Password",
]
# Properties that run expressions (such as `depends_on`, `fetch_from`) are not in this list.
PROPERTY_TYPES = {
	"label": "Data",
	"description": "Text",
	"reqd": "Check",
	"hidden": "Check",
	"read_only": "Check",
	"in_list_view": "Check",
	"in_standard_filter": "Check",
	"bold": "Check",
	"permlevel": "Int",
	"options": "Text",
	"default": "Text",
	"allow_on_submit": "Check",
	"print_hide": "Check",
}
PropertyName = Literal[
	"label",
	"description",
	"reqd",
	"hidden",
	"read_only",
	"in_list_view",
	"in_standard_filter",
	"bold",
	"permlevel",
	"options",
	"default",
	"allow_on_submit",
	"print_hide",
]
PERMISSION_TYPES = (
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"print",
	"email",
	"share",
	"select",
	"if_owner",
)


class AddCustomFieldArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	fieldname: str = Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")
	label: str = Field(min_length=1)
	fieldtype: FieldType
	description: str = Field(min_length=1)
	options: str | None = None
	reqd: bool = False
	insert_after: str | None = None
	permlevel: int = Field(default=0, ge=0, le=9)


class SetFieldPropertyArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	fieldname: str = Field(min_length=1)
	property: PropertyName
	value: str | int | bool


class SetRolePermissionArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	role: str = Field(min_length=1)
	permlevel: int = Field(default=0, ge=0, le=9)
	permissions: dict[str, bool]


class UserRoleArguments(ToolArguments):
	user: str = Field(min_length=1)
	role: str = Field(min_length=1)


class PurgeActionLogArguments(ToolArguments):
	older_than_days: int = Field(default=retention.MIN_DAYS, ge=retention.MIN_DAYS)


# A direct call has no version check. The approval flow always passes the expected version.
_UNCHECKED = object()


def _admin_meta(doctype: str):
	"""Runs the admin check and returns the definition of a DocType whose structure may change."""
	frappe.only_for(ADMIN_ROLE)
	if doctype in policy.ADMIN_TOOL_BLOCKED:
		raise ToolDenied(
			"blocked_doctype", _("DocType {0} is closed to AI tools.", context=CONTEXT).format(doctype)
		)
	return fields.get_meta(doctype)


def _spec(summary: str, doctype: str, name: str, version: str | None, changes: list) -> dict:
	return {
		"action": "admin",
		"summary": summary,
		"changes": changes,
		"target_doctype": doctype,
		"target_name": name,
		"target_version": version,
	}


def _verify(spec: dict, expected_version) -> None:
	"""Compares the target's version with the one in the preview right before writing.

	The caller first locks the actual target, then rebuilds the preview from current data.
	If the version differs, the approval was given for old data and the job does not run.
	"""
	if expected_version is _UNCHECKED:
		return
	if versioning.token(spec["target_version"]) != expected_version:
		raise ToolDenied("document_changed", _("The target changed after the preview.", context=CONTEXT))


def _grants_desk_access(role: str) -> bool:
	"""Does the role open the desk? The admin reads the role with their own permission."""
	filters = {"name": role, "desk_access": 1}
	return bool(frappe.get_list("Role", filters=filters, pluck="name", limit_page_length=1))


def _role_exists(role: str) -> bool:
	return bool(frappe.get_list("Role", filters={"name": role}, pluck="name", limit_page_length=1))


# --- custom field ---


def preview_custom_field(doctype: str, fieldname: str, **values) -> dict:
	meta = _admin_meta(doctype)
	if not frappe.has_permission("Custom Field", "create"):
		raise ToolDenied("permission", _("You may not create custom fields.", context=CONTEXT))
	if meta.has_field(fieldname):
		raise ToolDenied(
			"invalid_arguments", _("Field {0} already exists.", context=CONTEXT).format(fieldname)
		)
	if values["fieldtype"] in ("Select", "Link") and not values.get("options"):
		raise ToolDenied("invalid_arguments", _("Select and Link fields need options.", context=CONTEXT))
	if values["fieldtype"] == "Link":
		fields.get_meta(values["options"])
	if values.get("insert_after") and not meta.has_field(values["insert_after"]):
		raise ToolDenied(
			"invalid_arguments", _("insert_after names a field that does not exist.", context=CONTEXT)
		)
	changes = [
		{"fieldname": key, "label": None, "old": None, "new": value}
		for key, value in {"fieldname": fieldname, **values}.items()
		if value is not None
	]
	return _spec(
		f"Add custom field {fieldname} to {doctype}", "Custom Field", f"{doctype}-{fieldname}", None, changes
	)


def prepare_custom_field(doctype: str, fieldname: str, expected_version=_UNCHECKED, **values) -> dict:
	"""Pre-check: run every preview check again on the current definition."""
	frappe.clear_cache(doctype=doctype)
	_verify(preview_custom_field(doctype, fieldname, **values), expected_version)
	return {
		"doctype": "Custom Field",
		"dt": doctype,
		"fieldname": fieldname,
		"is_system_generated": 0,
		**{key: value for key, value in values.items() if value is not None},
	}


def write_custom_field(prepared: dict) -> dict:
	doc = frappe.get_doc(prepared)
	doc.insert()
	frappe.clear_cache(doctype=prepared["dt"])
	return {"name": doc.name}


def run_custom_field(doctype: str, fieldname: str, expected_version=_UNCHECKED, **values) -> dict:
	return write_custom_field(prepare_custom_field(doctype, fieldname, expected_version, **values))


# --- field property ---


def _property_value(property: str, value: str | int | bool) -> str:
	kind = PROPERTY_TYPES[property]
	if kind == "Check":
		if value not in (True, False, 0, 1):
			raise ToolDenied(
				"invalid_arguments", _("{0} takes true or false.", context=CONTEXT).format(property)
			)
		return str(int(bool(value)))
	if kind == "Int":
		if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9:
			raise ToolDenied(
				"invalid_arguments", _("{0} takes a number from 0 to 9.", context=CONTEXT).format(property)
			)
		return str(value)
	if not isinstance(value, str):
		raise ToolDenied("invalid_arguments", _("{0} takes text.", context=CONTEXT).format(property))
	return value


def _property_state(doctype: str, fieldname: str, property: str, *, for_update: bool = False) -> list:
	"""The "Property Setter" rows of one field property: name, value and `modified` of each.

	With `for_update` this is a locking read. It returns the latest committed rows and also locks
	the gap, so no other transaction can add the first row for this property until this one ends.
	If the database refuses the lock because a row changed after this transaction's snapshot,
	the target has changed and the action stops.
	"""
	if property not in PROPERTY_TYPES:
		raise ToolDenied("invalid_arguments", _("Unknown field: {0}", context=CONTEXT).format(property))
	key = {"doc_type": doctype, "field_name": fieldname, "property": property}
	try:
		rows = frappe.db.get_values(
			"Property Setter", key, ["name", "value", "modified"], for_update=for_update, as_dict=True
		)
		field_rows = _field_rows(doctype, fieldname, property, for_update=for_update)
	except frappe.QueryDeadlockError:
		raise ToolDenied(
			"document_changed", _("The target changed after the preview.", context=CONTEXT)
		) from None
	return [sorted([row.name, row.value, str(row.modified)] for row in rows), field_rows]


def _field_rows(doctype: str, fieldname: str, property: str, *, for_update: bool) -> list:
	"""The field's own definition rows: the property's value and `modified` of each.

	A standard field is a "DocField" row of the DocType, a custom one is a "Custom Field" record.
	`property` is a key of `PROPERTY_TYPES`, so it is a known column name.
	"""
	found = []
	for table, key in (
		("DocField", {"parent": doctype, "parenttype": "DocType", "fieldname": fieldname}),
		("Custom Field", {"dt": doctype, "fieldname": fieldname}),
	):
		rows = frappe.db.get_values(table, key, ["name", property, "modified"], for_update=for_update)
		found += sorted([table, row[0], row[1], str(row[2])] for row in rows)
	return found


def preview_field_property(doctype: str, fieldname: str, property: str, value: str | int | bool) -> dict:
	_admin_meta(doctype)
	return _field_property_spec(
		doctype, fieldname, property, value, _property_state(doctype, fieldname, property)
	)


def _field_property_spec(
	doctype: str, fieldname: str, property: str, value: str | int | bool, state: list
) -> dict:
	"""Build the preview. `state` is the property's stored rows, which the version is made of."""
	meta = _admin_meta(doctype)
	if not frappe.has_permission("Property Setter", "create"):
		raise ToolDenied("permission", _("You may not change field properties.", context=CONTEXT))
	field = meta.get_field(fieldname)
	if field is None:
		raise ToolDenied("invalid_arguments", _("Unknown field: {0}", context=CONTEXT).format(fieldname))
	if property == "options" and field.fieldtype != "Select":
		raise ToolDenied(
			"invalid_arguments", _("options can change only on a Select field.", context=CONTEXT)
		)
	new = _property_value(property, value)
	old = field.get(property)
	changes = [{"fieldname": f"{fieldname}.{property}", "label": field.label, "old": old, "new": new}]
	return _spec(
		f"Set {property} of {doctype}.{fieldname}",
		"Property Setter",
		f"{doctype}-{fieldname}-{property}",
		json.dumps({"shown": old, "stored": state}, default=str, sort_keys=True),
		changes,
	)


def prepare_field_property(
	doctype: str, fieldname: str, property: str, value: str | int | bool, expected_version=_UNCHECKED
) -> dict:
	"""Pre-check: read the current property under a lock, then compare it with the approved preview.

	The locking read comes before every plain read. It covers an existing row and the first insert.
	The compared version is built from the rows of that same locking read.
	"""
	state = _property_state(doctype, fieldname, property, for_update=True)
	new = _property_value(property, value)
	key = {"doc_type": doctype, "field_name": fieldname, "property": property}
	frappe.clear_cache(doctype=doctype)
	_verify(_field_property_spec(doctype, fieldname, property, value, state), expected_version)
	setters = state[0]
	return {"existing": setters[0][0] if setters else None, "value": new, "key": key}


def write_field_property(prepared: dict) -> dict:
	key = prepared["key"]
	if prepared["existing"]:
		doc = frappe.get_doc("Property Setter", prepared["existing"])
		doc.value = prepared["value"]
		doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"property_type": PROPERTY_TYPES[key["property"]],
				"value": prepared["value"],
				"is_system_generated": 0,
				**key,
			}
		).insert()
	frappe.clear_cache(doctype=key["doc_type"])
	return {"name": doc.name}


def run_field_property(
	doctype: str, fieldname: str, property: str, value: str | int | bool, expected_version=_UNCHECKED
) -> dict:
	return write_field_property(prepare_field_property(doctype, fieldname, property, value, expected_version))


# --- rol izni ---


def _permission_row(doctype: str, role: str, permlevel: int) -> dict | None:
	rows = [
		row
		for row in permission_manager.get_permissions(doctype=doctype, role=role)
		if (row.permlevel or 0) == permlevel
	]
	if len(rows) > 1:
		# Frappe does not say which of these rows it will pick on update.
		raise ToolDenied(
			"invalid_arguments",
			_(
				"This role has more than one rule at this level. Change it in the permission manager.",
				context=CONTEXT,
			),
		)
	return rows[0] if rows else None


def preview_role_permission(
	doctype: str, role: str, permissions: dict[str, bool], permlevel: int = 0
) -> dict:
	if (
		doctype in policy.ADMIN_TOOL_BLOCKED
		or doctype in policy.CODE_DOCTYPES
		or doctype in policy.ADMIN_DOCTYPES
	):
		# Granting permission on these types opens a path to code execution or privilege escalation.
		raise ToolDenied(
			"blocked_doctype",
			_("Permissions of DocType {0} do not change through AI.", context=CONTEXT).format(doctype),
		)
	if role in policy.PROTECTED_PERMISSION_ROLES:
		raise ToolDenied(
			"protected_role",
			_("Permissions of role {0} do not change through AI.", context=CONTEXT).format(role),
		)
	_admin_meta(doctype)
	if not _role_exists(role):
		raise ToolDenied("invalid_arguments", _("Unknown role: {0}", context=CONTEXT).format(role))
	if not permissions or set(permissions) - set(PERMISSION_TYPES):
		raise ToolDenied("invalid_arguments", _("permissions takes known permission types.", context=CONTEXT))
	row = _permission_row(doctype, role, permlevel)
	current = {ptype: int((row or {}).get(ptype) or 0) for ptype in PERMISSION_TYPES}
	# If there is no rule, Frappe creates the new rule with read permission
	# (`frappe.permissions.add_permission`). The preview shows this permission too.
	target = {**({} if row else {"read": True}), **permissions}
	changes = [
		{"fieldname": ptype, "label": None, "old": current[ptype], "new": int(value)}
		for ptype, value in target.items()
	]
	return _spec(
		f"Change what role {role} may do with {doctype} at level {permlevel}",
		"Custom DocPerm",
		f"{doctype}|{role}|{permlevel}",
		json.dumps(current if row else None, sort_keys=True),
		changes,
	)


def prepare_role_permission(
	doctype: str, role: str, permissions: dict[str, bool], permlevel: int = 0, expected_version=_UNCHECKED
) -> dict:
	"""Pre-check: lock the rule row, then compare the current rule with the previewed one."""
	frappe.only_for(ADMIN_ROLE)
	row = _permission_row(doctype, role, permlevel)
	if row is not None:
		store.lock_row("Custom DocPerm", row.name)
	frappe.clear_cache(doctype=doctype)
	_verify(preview_role_permission(doctype, role, permissions, permlevel), expected_version)
	return {
		"doctype": doctype,
		"role": role,
		"permlevel": permlevel,
		"permissions": permissions,
		"add": _permission_row(doctype, role, permlevel) is None,
	}


def write_role_permission(prepared: dict) -> dict:
	doctype, role, permlevel = prepared["doctype"], prepared["role"], prepared["permlevel"]
	# The `permission_manager` functions check the admin role themselves as well.
	if prepared["add"]:
		permission_manager.add(parent=doctype, role=role, permlevel=permlevel)
	for ptype, value in prepared["permissions"].items():
		permission_manager.update(
			doctype=doctype, role=role, permlevel=permlevel, ptype=ptype, value="1" if value else "0"
		)
	frappe.clear_cache(doctype=doctype)
	return {"name": f"{doctype}|{role}|{permlevel}"}


def run_role_permission(
	doctype: str, role: str, permissions: dict[str, bool], permlevel: int = 0, expected_version=_UNCHECKED
) -> dict:
	return write_role_permission(
		prepare_role_permission(doctype, role, permissions, permlevel, expected_version)
	)


# --- user role ---


def _user_for_role_change(user: str, role: str, *, adding: bool, lock: bool = False):
	frappe.only_for(ADMIN_ROLE)
	if role in policy.PROTECTED_ROLES or user in ("Administrator", "Guest"):
		raise ToolDenied(
			"protected_role", _("Role {0} does not change through AI.", context=CONTEXT).format(role)
		)
	if not _role_exists(role):
		raise ToolDenied("invalid_arguments", _("Unknown role: {0}", context=CONTEXT).format(role))
	doc = frappe.get_doc("User", user, for_update=lock)
	doc.check_permission("write")
	if adding and doc.user_type == "Website User" and _grants_desk_access(role):
		# G-16: an end user never gets a role with `desk_access`. Frappe would make the user a
		# System User on save (`frappe/core/doctype/user/user.py`, `set_system_user`).
		raise ToolDenied(
			"desk_role_for_end_user",
			_("Role {0} gives desk access. An end user cannot have it.", context=CONTEXT).format(role),
		)
	has_role = role in {row.role for row in doc.roles}
	if adding == has_role:
		message = (
			_("The user already has this role.", context=CONTEXT)
			if adding
			else _("The user does not have this role.", context=CONTEXT)
		)
		raise ToolDenied("invalid_arguments", message)
	return doc


def _role_spec(user: str, role: str, *, adding: bool, lock: bool = False) -> tuple[dict, object]:
	doc = _user_for_role_change(user, role, adding=adding, lock=lock)
	summary = f"Give role {role} to {user}" if adding else f"Take role {role} away from {user}"
	change = {
		"fieldname": "roles",
		"label": "Roles",
		"old": None if adding else role,
		"new": role if adding else None,
	}
	return _spec(summary, "User", user, str(doc.modified), [change]), doc


def preview_assign_role(user: str, role: str) -> dict:
	return _role_spec(user, role, adding=True)[0]


def prepare_assign_role(user: str, role: str, expected_version=_UNCHECKED) -> tuple:
	spec, doc = _role_spec(user, role, adding=True, lock=True)
	_verify(spec, expected_version)
	return doc, role


def write_assign_role(prepared: tuple) -> dict:
	doc, role = prepared
	doc.add_roles(role)
	return {"name": doc.name}


def run_assign_role(user: str, role: str, expected_version=_UNCHECKED) -> dict:
	return write_assign_role(prepare_assign_role(user, role, expected_version))


def preview_remove_role(user: str, role: str) -> dict:
	return _role_spec(user, role, adding=False)[0]


def prepare_remove_role(user: str, role: str, expected_version=_UNCHECKED) -> tuple:
	spec, doc = _role_spec(user, role, adding=False, lock=True)
	_verify(spec, expected_version)
	return doc, role


def write_remove_role(prepared: tuple) -> dict:
	doc, role = prepared
	doc.remove_roles(role)
	return {"name": doc.name}


def run_remove_role(user: str, role: str, expected_version=_UNCHECKED) -> dict:
	return write_remove_role(prepare_remove_role(user, role, expected_version))


# --- manually started command: log cleanup ---


def preview_purge(older_than_days: int = retention.MIN_DAYS) -> dict:
	counts = retention.purge(older_than_days, dry_run=True)
	return {
		"action": "admin",
		"summary": (
			f"Delete AI Action Log records older than {older_than_days} days, AI Usage Log records "
			f"older than {retention.MIN_DAYS} days, and proposals {retention.PROPOSAL_DAYS} days after "
			"their decision or expiry. Cannot be undone."
		),
		# The numbers are what one run deletes. For the usage log the gateway reports how many
		# records wait (`eligible`). It deletes them in batches.
		"details": counts,
	}


def prepare_purge(older_than_days: int = retention.MIN_DAYS) -> int:
	"""Pre-check: the admin role and the retention period. Counts only."""
	retention.purge(older_than_days, dry_run=True)
	return older_than_days


def write_purge(older_than_days: int) -> dict:
	return retention.purge(older_than_days, dry_run=False)


def run_purge(older_than_days: int = retention.MIN_DAYS) -> dict:
	return write_purge(prepare_purge(older_than_days))
