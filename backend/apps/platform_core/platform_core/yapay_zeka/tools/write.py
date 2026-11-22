"""Yazma araçları. Her aracın bir önizleme işlevi ve bir yürütme işlevi vardır.

Model yalnız önizlemeyi tetikler. Yürütme işlevi yalnız insan onayından sonra,
`proposals.approve` içinden çağrılır (G-86). Yürütme izni yeniden denetler.
"""

from typing import Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from pydantic import Field

from platform_core.yapay_zeka import fields, policy
from platform_core.yapay_zeka.errors import ToolDenied

ROW_RESERVED_KEYS = frozenset({"parenttype", "parentfield"})
RESERVED_KEYS = frozenset(
	{"doctype", "docstatus", "owner", "creation", "modified", "modified_by", "idx", "parent"}
)


class CreateDocumentArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	data: dict[str, Any]


class UpdateDocumentArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	name: str = Field(min_length=1)
	data: dict[str, Any]


class DocumentTargetArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	name: str = Field(min_length=1)


def writable_meta(doctype: str):
	"""DocType genel yazma araçlarına açıksa tanımını döner."""
	# The name lists are checked before the definition is loaded. A closed DocType answers the
	# same way whether or not it is installed on this site.
	if doctype in policy.WRITE_BLOCKED:
		raise ToolDenied("blocked_doctype", _("DocType {0} is closed to AI write tools.").format(doctype))
	if doctype in policy.ADMIN_DOCTYPES:
		raise ToolDenied("admin_only", _("DocType {0} changes only through admin tools.").format(doctype))
	if policy.is_closed_by_app(doctype):
		raise ToolDenied("blocked_doctype", _("DocType {0} is closed to AI write tools.").format(doctype))
	meta = fields.get_meta(doctype)
	if policy.is_framework_doctype(meta):
		raise ToolDenied(
			"blocked_doctype", _("Framework DocType {0} is closed to AI write tools.").format(doctype)
		)
	if meta.istable:
		raise ToolDenied("invalid_arguments", _("Change child rows through their parent document."))
	return meta


def check_data(meta, data: dict[str, Any], *, doc=None, allow_name: bool = False) -> None:
	"""Yazılacak alanları tanıma ve kullanıcının iznine göre doğrular.

	`doc` güncellenen kayıttır. Yeni kayıtta `None` olur. Alt tablo satırları bu kayda göre denetlenir.
	"""
	if not data:
		raise ToolDenied("invalid_arguments", _("data must name at least one field."))
	can_write = fields.writable(meta)
	for key, value in data.items():
		if key == "name" and allow_name and meta.autoname == "prompt":
			continue
		field = meta.get_field(key)
		if key in RESERVED_KEYS or key == "name" or field is None:
			raise ToolDenied("invalid_arguments", _("Field {0} cannot be set.").format(key))
		if policy.is_secret_field(field):
			raise ToolDenied("secret_field", _("Field {0} is secret. A human enters it.").format(key))
		if key not in can_write:
			raise ToolDenied("field_not_permitted", _("You may not write field {0}.").format(key))
		if field.fieldtype in ("Table", "Table MultiSelect"):
			_check_rows(meta, field, value, doc)


def _check_rows(meta, field, rows: Any, doc) -> None:
	"""Alt tablo satırlarını denetler.

	Frappe satırı yalnız adıyla günceller ve ana kaydı satıra kendisi yazar
	(`frappe/model/document.py` içinde `_init_child` ve `update_child_table`). Bu yüzden:

	- Satır adı yalnız bu ana kaydın bu tablosundaki bir satırın adı olabilir.
	- Yeni kayıtta ve yeni satırda ad istemciden alınmaz.
	- Satır alanlarında da alan düzeyi yazma izni aranır. Frappe yeni kayıtta bunu atlar.
	"""
	if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
		raise ToolDenied("invalid_arguments", _("Field {0} takes a list of rows.").format(field.fieldname))
	child_meta = frappe.get_meta(field.options)
	can_write = fields.writable(child_meta, parenttype=meta.name)
	own_rows = {row.name for row in (doc.get(field.fieldname) or [])} if doc is not None else set()
	seen = set()
	for row in rows:
		for key in row:
			if key == "name":
				name = row[key]
				if not isinstance(name, str) or name not in own_rows or name in seen:
					raise ToolDenied(
						"invalid_arguments",
						_("A row name must be an existing row of this document. New rows carry no name."),
					)
				seen.add(name)
				continue
			child_field = child_meta.get_field(key)
			if child_field is None or key in RESERVED_KEYS or key in ROW_RESERVED_KEYS:
				raise ToolDenied("invalid_arguments", _("Row field {0} cannot be set.").format(key))
			if policy.is_secret_field(child_field):
				raise ToolDenied("secret_field", _("Field {0} is secret. A human enters it.").format(key))
			if key not in can_write:
				raise ToolDenied("field_not_permitted", _("You may not write row field {0}.").format(key))
			if child_field.fieldtype in ("Table", "Table MultiSelect"):
				raise ToolDenied("invalid_arguments", _("Rows cannot carry their own tables."))


def _spec(action: str, summary: str, doctype: str, doc=None, changes: list | None = None) -> dict:
	return {
		"action": action,
		"summary": summary,
		"changes": changes or [],
		"target_doctype": doctype,
		"target_name": doc.name if doc is not None else None,
		"target_version": str(doc.modified) if doc is not None else None,
	}


def _load(doctype: str, name: str, ptype: str, expected_version: str | None = None):
	"""Kaydı yükler ve izni denetler.

	Yürütme `expected_version` verir. O zaman kayıt satır kilidiyle okunur ve önizlemedeki
	sürümle karşılaştırılır. Böylece araya giren değişikliğin üstüne yazılmaz.
	"""
	meta = writable_meta(doctype)
	doc = frappe.get_doc(doctype, name, for_update=expected_version is not None)
	doc.check_permission(ptype)
	if expected_version is not None and str(doc.modified) != expected_version:
		raise ToolDenied("document_changed", _("The document changed after the preview."))
	return meta, doc


# --- oluşturma ---


def preview_create(doctype: str, data: dict[str, Any]) -> dict:
	meta = writable_meta(doctype)
	if not frappe.has_permission(doctype, "create"):
		raise ToolDenied("permission", _("You may not create {0}.").format(doctype))
	check_data(meta, data, allow_name=True)
	changes = [
		{"fieldname": key, "label": getattr(meta.get_field(key), "label", None), "old": None, "new": value}
		for key, value in data.items()
	]
	return _spec("create", f"Create a new {doctype}", doctype, changes=changes)


def prepare_create(doctype: str, data: dict[str, Any]) -> tuple:
	"""Pre-check for a create. Calls no Frappe document method."""
	meta = writable_meta(doctype)
	if not frappe.has_permission(doctype, "create"):
		raise ToolDenied("permission", _("You may not create {0}.").format(doctype))
	check_data(meta, data, allow_name=True)
	return doctype, data


def write_create(prepared: tuple) -> dict:
	doctype, data = prepared
	doc = frappe.new_doc(doctype)
	doc.update(data)
	doc.insert()
	return {"name": doc.name}


def run_create(doctype: str, data: dict[str, Any]) -> dict:
	return write_create(prepare_create(doctype, data))


# --- güncelleme ---


def preview_update(doctype: str, name: str, data: dict[str, Any]) -> dict:
	meta, doc = _load(doctype, name, "write")
	check_data(meta, data, doc=doc)
	can_read = fields.readable(meta)
	changes = [
		{
			"fieldname": key,
			"label": meta.get_field(key).label,
			"old": _old_value(meta, doc, key) if key in can_read else None,
			"new": value,
		}
		for key, value in data.items()
	]
	return _spec("update", f"Update {doctype} {name}", doctype, doc, changes)


def _old_value(meta, doc, key: str) -> Any:
	"""Önizlemedeki eski değer. Alt tabloda satırların okunabilir alanları gösterilir.

	Gönderilen satır listesi tablonun tamamının yerine geçer. İnsan silinecek satırı da görmelidir.
	"""
	value = doc.get(key)
	if not isinstance(value, list):
		return value
	child_meta = frappe.get_meta(meta.get_field(key).options)
	return [fields.clean(row.as_dict(), child_meta, meta.name) for row in value]


def prepare_update(
	doctype: str, name: str, data: dict[str, Any], expected_version: str | None = None
) -> tuple:
	"""Pre-check for an update: lock the row, re-check permission, version and every field."""
	meta, doc = _load(doctype, name, "write", expected_version)
	check_data(meta, data, doc=doc)
	return doc, data


def write_update(prepared: tuple) -> dict:
	doc, data = prepared
	doc.update(data)
	doc.save()
	return {"name": doc.name}


def run_update(doctype: str, name: str, data: dict[str, Any], expected_version: str | None = None) -> dict:
	return write_update(prepare_update(doctype, name, data, expected_version))


# --- onaya gönderme, iptal, silme ---


def _check_submit(meta, doc) -> None:
	if not meta.is_submittable or doc.docstatus != 0:
		raise ToolDenied("invalid_arguments", _("Only a draft of a submittable DocType can be submitted."))


def _check_cancel(doc) -> None:
	if doc.docstatus != 1:
		raise ToolDenied("invalid_arguments", _("Only a submitted document can be cancelled."))


def _check_delete(doc) -> None:
	if doc.docstatus == 1:
		raise ToolDenied("invalid_arguments", _("Cancel a submitted document before deleting it."))


def preview_submit(doctype: str, name: str) -> dict:
	meta, doc = _load(doctype, name, "submit")
	_check_submit(meta, doc)
	return _spec("submit", f"Submit {doctype} {name}", doctype, doc)


def prepare_submit(doctype: str, name: str, expected_version: str | None = None):
	meta, doc = _load(doctype, name, "submit", expected_version)
	_check_submit(meta, doc)
	return doc


def write_submit(doc) -> dict:
	doc.submit()
	return {"name": doc.name}


def run_submit(doctype: str, name: str, expected_version: str | None = None) -> dict:
	return write_submit(prepare_submit(doctype, name, expected_version))


def preview_cancel(doctype: str, name: str) -> dict:
	_meta, doc = _load(doctype, name, "cancel")
	_check_cancel(doc)
	return _spec("cancel", f"Cancel {doctype} {name}", doctype, doc)


def prepare_cancel(doctype: str, name: str, expected_version: str | None = None):
	_meta, doc = _load(doctype, name, "cancel", expected_version)
	_check_cancel(doc)
	return doc


def write_cancel(doc) -> dict:
	doc.cancel()
	return {"name": doc.name}


def run_cancel(doctype: str, name: str, expected_version: str | None = None) -> dict:
	return write_cancel(prepare_cancel(doctype, name, expected_version))


def preview_delete(doctype: str, name: str) -> dict:
	_meta, doc = _load(doctype, name, "delete")
	_check_delete(doc)
	return _spec("delete", f"Delete {doctype} {name}", doctype, doc)


def prepare_delete(doctype: str, name: str, expected_version: str | None = None):
	_meta, doc = _load(doctype, name, "delete", expected_version)
	_check_delete(doc)
	return doc


def write_delete(doc) -> dict:
	# `frappe.delete_doc` checks the delete permission and linked documents itself as well.
	frappe.delete_doc(doc.doctype, doc.name)
	return {"name": doc.name}


def run_delete(doctype: str, name: str, expected_version: str | None = None) -> dict:
	return write_delete(prepare_delete(doctype, name, expected_version))
