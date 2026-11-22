"""Alan düzeyi yönetimi. Frappe'nin izin seviyesini hazır işlevlerle ayarlar (karar notu 8. bölüm)."""

import frappe
from frappe import _
from frappe.core.doctype.custom_docperm.custom_docperm import update_custom_docperm
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.custom.doctype.property_setter.property_setter import delete_property_setter, make_property_setter
from frappe.permissions import add_permission, setup_custom_perms
from frappe.utils import cint

from platform_core.erisim.rules import PROTECTED_DOCTYPES

MAX_LEVEL = 9


def _require_admin(doctype: str) -> None:
	frappe.only_for("System Manager")
	if not frappe.db.exists("DocType", doctype, cache=True):
		frappe.throw(_("Document type {0} not found.").format(doctype), frappe.DoesNotExistError)
	if doctype in PROTECTED_DOCTYPES:
		# Bu türlerde alan kapatmak izin yönetimini kilitleyebilir.
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
			# Yetki yukarıda `only_for` ile denetlendi. Bu işlev izin denetlemez.
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

	# İlk değişiklikte Frappe rol izinlerini “Custom DocPerm” tablosuna kopyalar.
	setup_custom_perms(doctype)
	filters = {"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0}
	existing = frappe.db.get_value("Custom DocPerm", filters)
	if not read:
		if existing:
			frappe.delete_doc("Custom DocPerm", existing)
	else:
		if not existing:
			existing = add_permission(doctype, role, permlevel, "read")
		# Satır adla güncellenir. Rol ve seviyeyle arama `if_owner` satırını da bulabilir.
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
