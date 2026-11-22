"""Kullanıcının hangi alanı okuyup yazabileceğini hesaplar ve yanıtı temizler."""

from typing import TYPE_CHECKING, Any

import frappe
from frappe import _

from platform_core.yapay_zeka import policy
from platform_core.yapay_zeka.errors import ToolDenied

if TYPE_CHECKING:
	from frappe.model.meta import Meta

STANDARD_FIELDS = ("name", "owner", "creation", "modified", "modified_by", "docstatus", "idx")


def get_meta(doctype: str) -> "Meta":
	try:
		return frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		frappe.clear_messages()
		raise ToolDenied("unknown_doctype", _("DocType {0} does not exist.").format(doctype)) from None


def _permitted(meta: "Meta", ptype: str, parenttype: str | None) -> set[str]:
	"""İzinli alan adları. Alt tablo alanı da izin seviyesine göre girer.

	Frappe'nin `get_permitted_fieldnames` işlevi tablo alanlarını saymaz. Tablo alanının
	izni, alanın izin seviyesinin kullanıcıya açık olmasıdır.
	"""
	names = set(meta.get_permitted_fieldnames(parenttype=parenttype, permission_type=ptype))
	if not meta.istable:
		levels = set(meta.get_permlevel_access(permission_type=ptype))
		names |= {field.fieldname for field in meta.get_table_fields() if (field.permlevel or 0) in levels}
	return names


def readable(meta: "Meta", parenttype: str | None = None) -> set[str]:
	"""Kullanıcının okuyabildiği, gizli olmayan alanlar."""
	permitted = _permitted(meta, "read", parenttype)
	names = {
		field.fieldname
		for field in meta.fields
		if field.fieldname in permitted and not policy.is_secret_field(field)
	}
	return names | set(STANDARD_FIELDS)


def writable(meta: "Meta", parenttype: str | None = None) -> set[str]:
	"""Kullanıcının yazabildiği, gizli olmayan alanlar."""
	permitted = _permitted(meta, "write", parenttype)
	return {
		field.fieldname
		for field in meta.fields
		if field.fieldname in permitted and not policy.is_secret_field(field)
	}


def check_readable(meta: "Meta", fieldname: str) -> None:
	"""Alan okunamıyorsa çağrıyı reddeder. Süzgeç ve sıralama alanları da buradan geçer."""
	if fieldname in STANDARD_FIELDS:
		return
	field = meta.get_field(fieldname)
	if field is None or not fieldname.isidentifier():
		raise ToolDenied("invalid_arguments", _("Unknown field: {0}").format(fieldname))
	if policy.is_secret_field(field):
		raise ToolDenied("secret_field", _("Field {0} is secret.").format(fieldname))
	if fieldname not in readable(meta):
		raise ToolDenied("field_not_permitted", _("You may not read field {0}.").format(fieldname))


def clean(data: dict[str, Any], meta: "Meta", parenttype: str | None = None) -> dict[str, Any]:
	"""Kayıt sözlüğünde yalnız okunabilir alanları bırakır. Alt tabloları da temizler.

	Frappe izin seviyesi yüksek alanın değerini boşaltır ama anahtarı bırakır.
	Burada anahtar da çıkar. Gizli alanlar ve iç anahtarlar da çıkar.
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
