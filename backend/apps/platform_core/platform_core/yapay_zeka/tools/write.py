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
	meta = fields.get_meta(doctype)
	if doctype in policy.WRITE_BLOCKED:
		raise ToolDenied("blocked_doctype", _("DocType {0} is closed to AI write tools.").format(doctype))
	if doctype in policy.ADMIN_DOCTYPES:
		raise ToolDenied("admin_only", _("DocType {0} changes only through admin tools.").format(doctype))
	if policy.is_framework_doctype(meta):
		raise ToolDenied(
			"blocked_doctype", _("Framework DocType {0} is closed to AI write tools.").format(doctype)
		)
	if meta.istable:
		raise ToolDenied("invalid_arguments", _("Change child rows through their parent document."))
	return meta


def check_data(meta, data: dict[str, Any], *, allow_name: bool = False) -> None:
	"""Yazılacak alanları tanıma ve kullanıcının iznine göre doğrular."""
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
			_check_rows(field, value)


def _check_rows(field, rows: Any) -> None:
	if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
		raise ToolDenied("invalid_arguments", _("Field {0} takes a list of rows.").format(field.fieldname))
	child_meta = frappe.get_meta(field.options)
	for row in rows:
		for key in row:
			child_field = child_meta.get_field(key)
			if child_field is None and key != "name":
				raise ToolDenied("invalid_arguments", _("Field {0} cannot be set.").format(key))
			if child_field is not None and policy.is_secret_field(child_field):
				raise ToolDenied("secret_field", _("Field {0} is secret. A human enters it.").format(key))


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


def run_create(doctype: str, data: dict[str, Any]) -> dict:
	doc = frappe.new_doc(doctype)
	doc.update(data)
	doc.insert()
	return {"name": doc.name}


# --- güncelleme ---


def preview_update(doctype: str, name: str, data: dict[str, Any]) -> dict:
	meta, doc = _load(doctype, name, "write")
	check_data(meta, data)
	can_read = fields.readable(meta)
	changes = [
		{
			"fieldname": key,
			"label": meta.get_field(key).label,
			"old": doc.get(key) if key in can_read and not isinstance(doc.get(key), list) else None,
			"new": value,
		}
		for key, value in data.items()
	]
	return _spec("update", f"Update {doctype} {name}", doctype, doc, changes)


def run_update(doctype: str, name: str, data: dict[str, Any], expected_version: str | None = None) -> dict:
	_meta, doc = _load(doctype, name, "write", expected_version)
	doc.update(data)
	doc.save()
	return {"name": doc.name}


# --- onaya gönderme, iptal, silme ---


def preview_submit(doctype: str, name: str) -> dict:
	meta, doc = _load(doctype, name, "submit")
	if not meta.is_submittable or doc.docstatus != 0:
		raise ToolDenied("invalid_arguments", _("Only a draft of a submittable DocType can be submitted."))
	return _spec("submit", f"Submit {doctype} {name}", doctype, doc)


def run_submit(doctype: str, name: str, expected_version: str | None = None) -> dict:
	_meta, doc = _load(doctype, name, "submit", expected_version)
	doc.submit()
	return {"name": doc.name}


def preview_cancel(doctype: str, name: str) -> dict:
	_meta, doc = _load(doctype, name, "cancel")
	if doc.docstatus != 1:
		raise ToolDenied("invalid_arguments", _("Only a submitted document can be cancelled."))
	return _spec("cancel", f"Cancel {doctype} {name}", doctype, doc)


def run_cancel(doctype: str, name: str, expected_version: str | None = None) -> dict:
	_meta, doc = _load(doctype, name, "cancel", expected_version)
	doc.cancel()
	return {"name": doc.name}


def preview_delete(doctype: str, name: str) -> dict:
	_meta, doc = _load(doctype, name, "delete")
	if doc.docstatus == 1:
		raise ToolDenied("invalid_arguments", _("Cancel a submitted document before deleting it."))
	return _spec("delete", f"Delete {doctype} {name}", doctype, doc)


def run_delete(doctype: str, name: str, expected_version: str | None = None) -> dict:
	_load(doctype, name, "delete", expected_version)
	# `frappe.delete_doc` silme iznini ve bağlı kayıtları kendisi de denetler.
	frappe.delete_doc(doctype, name)
	return {"name": name}
