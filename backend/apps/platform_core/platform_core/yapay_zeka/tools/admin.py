"""Yönetim araçları: özel alan, alan ayarı, rol ve izin değişikliği.

Yalnız “System Manager” rolüne açıktır. Her araç önizleme üretir ve insan onayı ister.
Yürütme Frappe'nin kendi yönetim yollarını kullanır. Bu yollar yetkiyi yeniden denetler.
"""

import json
from typing import Literal

import frappe
from frappe import _
from frappe.core.page.permission_manager import permission_manager
from frappe.mcp.tools import ToolArguments
from pydantic import Field

from platform_core.yapay_zeka import fields, policy, retention, store, versioning
from platform_core.yapay_zeka.errors import ToolDenied

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
# İfade çalıştıran ayarlar (`depends_on`, `fetch_from` gibi) bu listede yoktur.
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


# Doğrudan çağrıda sürüm denetimi yoktur. Onay akışı beklenen sürümü her zaman verir.
_UNCHECKED = object()


def _admin_meta(doctype: str):
	"""Yönetici denetimini yapar ve yapısı değişebilen DocType'ın tanımını döner."""
	frappe.only_for(ADMIN_ROLE)
	meta = fields.get_meta(doctype)
	if doctype in policy.CREDENTIAL_DOCTYPES or doctype in policy.LAYER_DOCTYPES:
		raise ToolDenied("blocked_doctype", _("DocType {0} is closed to AI tools.").format(doctype))
	return meta


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
	"""Yazmadan hemen önce hedefin sürümünü önizlemedekiyle karşılaştırır.

	Çağıran önce asıl hedefi kilitler, sonra önizlemeyi güncel veriyle yeniden üretir.
	Sürüm farklıysa onay eski veriye verilmiştir ve iş yürümez.
	"""
	if expected_version is _UNCHECKED:
		return
	if versioning.token(spec["target_version"]) != expected_version:
		raise ToolDenied("document_changed", _("The target changed after the preview."))


def _role_exists(role: str) -> bool:
	return bool(frappe.get_list("Role", filters={"name": role}, pluck="name", limit_page_length=1))


# --- özel alan ---


def preview_custom_field(doctype: str, fieldname: str, **values) -> dict:
	meta = _admin_meta(doctype)
	if not frappe.has_permission("Custom Field", "create"):
		raise ToolDenied("permission", _("You may not create custom fields."))
	if meta.has_field(fieldname):
		raise ToolDenied("invalid_arguments", _("Field {0} already exists.").format(fieldname))
	if values["fieldtype"] in ("Select", "Link") and not values.get("options"):
		raise ToolDenied("invalid_arguments", _("Select and Link fields need options."))
	if values["fieldtype"] == "Link":
		fields.get_meta(values["options"])
	if values.get("insert_after") and not meta.has_field(values["insert_after"]):
		raise ToolDenied("invalid_arguments", _("insert_after names a field that does not exist."))
	changes = [
		{"fieldname": key, "label": None, "old": None, "new": value}
		for key, value in {"fieldname": fieldname, **values}.items()
		if value is not None
	]
	return _spec(
		f"Add custom field {fieldname} to {doctype}", "Custom Field", f"{doctype}-{fieldname}", None, changes
	)


def run_custom_field(doctype: str, fieldname: str, expected_version=_UNCHECKED, **values) -> dict:
	# Önizlemenin bütün denetimleri güncel tanımla yeniden çalışır. Alan arada eklendiyse iş durur.
	frappe.clear_cache(doctype=doctype)
	_verify(preview_custom_field(doctype, fieldname, **values), expected_version)
	doc = frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": fieldname,
			"is_system_generated": 0,
			**{key: value for key, value in values.items() if value is not None},
		}
	)
	doc.insert()
	frappe.clear_cache(doctype=doctype)
	return {"name": doc.name}


# --- alan ayarı ---


def _property_value(property: str, value: str | int | bool) -> str:
	kind = PROPERTY_TYPES[property]
	if kind == "Check":
		if value not in (True, False, 0, 1):
			raise ToolDenied("invalid_arguments", _("{0} takes true or false.").format(property))
		return str(int(bool(value)))
	if kind == "Int":
		if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9:
			raise ToolDenied("invalid_arguments", _("{0} takes a number from 0 to 9.").format(property))
		return str(value)
	if not isinstance(value, str):
		raise ToolDenied("invalid_arguments", _("{0} takes text.").format(property))
	return value


def preview_field_property(doctype: str, fieldname: str, property: str, value: str | int | bool) -> dict:
	meta = _admin_meta(doctype)
	if not frappe.has_permission("Property Setter", "create"):
		raise ToolDenied("permission", _("You may not change field properties."))
	field = meta.get_field(fieldname)
	if field is None:
		raise ToolDenied("invalid_arguments", _("Unknown field: {0}").format(fieldname))
	if property == "options" and field.fieldtype != "Select":
		raise ToolDenied("invalid_arguments", _("options can change only on a Select field."))
	new = _property_value(property, value)
	old = field.get(property)
	changes = [{"fieldname": f"{fieldname}.{property}", "label": field.label, "old": old, "new": new}]
	return _spec(
		f"Set {property} of {doctype}.{fieldname}",
		"Property Setter",
		f"{doctype}-{fieldname}-{property}",
		json.dumps(old, default=str),
		changes,
	)


def run_field_property(
	doctype: str, fieldname: str, property: str, value: str | int | bool, expected_version=_UNCHECKED
) -> dict:
	_admin_meta(doctype)
	new = _property_value(property, value)
	key = {"doc_type": doctype, "field_name": fieldname, "property": property}
	existing = frappe.get_list("Property Setter", filters=key, pluck="name", limit_page_length=1)
	# Asıl hedef kilitlenir, sonra değer güncel tanımdan yeniden okunur.
	if existing:
		store.lock_row("Property Setter", existing[0])
	frappe.clear_cache(doctype=doctype)
	_verify(preview_field_property(doctype, fieldname, property, value), expected_version)
	if existing:
		doc = frappe.get_doc("Property Setter", existing[0])
		doc.value = new
		doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"property_type": PROPERTY_TYPES[property],
				"value": new,
				"is_system_generated": 0,
				**key,
			}
		).insert()
	frappe.clear_cache(doctype=doctype)
	return {"name": doc.name}


# --- rol izni ---


def _permission_row(doctype: str, role: str, permlevel: int) -> dict | None:
	rows = [
		row
		for row in permission_manager.get_permissions(doctype=doctype, role=role)
		if (row.permlevel or 0) == permlevel
	]
	if len(rows) > 1:
		# Frappe güncellemede bu satırlardan hangisini seçeceğini belirtmez.
		raise ToolDenied(
			"invalid_arguments",
			_("This role has more than one rule at this level. Change it in the permission manager."),
		)
	return rows[0] if rows else None


def preview_role_permission(
	doctype: str, role: str, permissions: dict[str, bool], permlevel: int = 0
) -> dict:
	_admin_meta(doctype)
	if doctype in policy.CODE_DOCTYPES or doctype in policy.ADMIN_DOCTYPES:
		# Bu türlerde izin vermek, kod çalıştırma ya da yetki yükseltme yolu açar.
		raise ToolDenied(
			"blocked_doctype", _("Permissions of DocType {0} do not change through AI.").format(doctype)
		)
	if role in policy.PROTECTED_PERMISSION_ROLES:
		raise ToolDenied(
			"protected_role", _("Permissions of role {0} do not change through AI.").format(role)
		)
	if not _role_exists(role):
		raise ToolDenied("invalid_arguments", _("Unknown role: {0}").format(role))
	if not permissions or set(permissions) - set(PERMISSION_TYPES):
		raise ToolDenied("invalid_arguments", _("permissions takes known permission types."))
	row = _permission_row(doctype, role, permlevel)
	current = {ptype: int((row or {}).get(ptype) or 0) for ptype in PERMISSION_TYPES}
	# Kural yoksa Frappe yeni kuralı okuma izniyle açar (`frappe.permissions.add_permission`).
	# Önizleme bu izni de gösterir.
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


def run_role_permission(
	doctype: str, role: str, permissions: dict[str, bool], permlevel: int = 0, expected_version=_UNCHECKED
) -> dict:
	frappe.only_for(ADMIN_ROLE)
	row = _permission_row(doctype, role, permlevel)
	if row is not None:
		store.lock_row("Custom DocPerm", row.name)
	frappe.clear_cache(doctype=doctype)
	_verify(preview_role_permission(doctype, role, permissions, permlevel), expected_version)
	# `permission_manager` işlevleri yönetici rolünü kendileri de denetler.
	if _permission_row(doctype, role, permlevel) is None:
		permission_manager.add(parent=doctype, role=role, permlevel=permlevel)
	for ptype, value in permissions.items():
		permission_manager.update(
			doctype=doctype, role=role, permlevel=permlevel, ptype=ptype, value="1" if value else "0"
		)
	frappe.clear_cache(doctype=doctype)
	return {"name": f"{doctype}|{role}|{permlevel}"}


# --- kullanıcı rolü ---


def _user_for_role_change(user: str, role: str, *, adding: bool, lock: bool = False):
	frappe.only_for(ADMIN_ROLE)
	if role in policy.PROTECTED_ROLES or user in ("Administrator", "Guest"):
		raise ToolDenied("protected_role", _("Role {0} does not change through AI.").format(role))
	if not _role_exists(role):
		raise ToolDenied("invalid_arguments", _("Unknown role: {0}").format(role))
	doc = frappe.get_doc("User", user, for_update=lock)
	doc.check_permission("write")
	has_role = role in {row.role for row in doc.roles}
	if adding == has_role:
		message = _("The user already has this role.") if adding else _("The user does not have this role.")
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


def run_assign_role(user: str, role: str, expected_version=_UNCHECKED) -> dict:
	spec, doc = _role_spec(user, role, adding=True, lock=True)
	_verify(spec, expected_version)
	doc.add_roles(role)
	return {"name": user}


def preview_remove_role(user: str, role: str) -> dict:
	return _role_spec(user, role, adding=False)[0]


def run_remove_role(user: str, role: str, expected_version=_UNCHECKED) -> dict:
	spec, doc = _role_spec(user, role, adding=False, lock=True)
	_verify(spec, expected_version)
	doc.remove_roles(role)
	return {"name": user}


# --- elle başlatılan komut: günlük temizliği ---


def preview_purge(older_than_days: int = retention.MIN_DAYS) -> dict:
	counts = retention.purge(older_than_days, dry_run=True)
	return {
		"action": "admin",
		"summary": f"Delete AI action logs and proposals older than {older_than_days} days. Cannot be undone.",
		"details": counts,
	}


def run_purge(older_than_days: int = retention.MIN_DAYS) -> dict:
	return retention.purge(older_than_days, dry_run=False)
