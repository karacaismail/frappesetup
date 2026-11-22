"""Write tools. Each tool has a preview function and an execute function.

The model only triggers the preview. The execute function is called only after human approval,
from inside `proposals.approve` (G-86). Execution checks the permission again.
"""

from typing import Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from pydantic import Field

from platform_core.yapay_zeka import fields, policy
from platform_core.yapay_zeka.errors import CONTEXT, ToolDenied

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
	"""Returns the definition if the DocType is open to the general write tools."""
	# The name lists are checked before the definition is loaded. A closed DocType answers the
	# same way whether or not it is installed on this site.
	if doctype in policy.WRITE_BLOCKED:
		raise ToolDenied(
			"blocked_doctype", _("DocType {0} is closed to AI write tools.", context=CONTEXT).format(doctype)
		)
	if doctype in policy.ADMIN_DOCTYPES:
		raise ToolDenied(
			"admin_only", _("DocType {0} changes only through admin tools.", context=CONTEXT).format(doctype)
		)
	if policy.is_closed_by_app(doctype):
		raise ToolDenied(
			"blocked_doctype", _("DocType {0} is closed to AI write tools.", context=CONTEXT).format(doctype)
		)
	meta = fields.get_meta(doctype)
	if policy.is_framework_doctype(meta):
		raise ToolDenied(
			"blocked_doctype",
			_("Framework DocType {0} is closed to AI write tools.", context=CONTEXT).format(doctype),
		)
	if meta.istable:
		raise ToolDenied(
			"invalid_arguments", _("Change child rows through their parent document.", context=CONTEXT)
		)
	return meta


def check_data(meta, data: dict[str, Any], *, doc=None, allow_name: bool = False) -> None:
	"""Validates the fields to write against the definition and the user's permission.

	`doc` is the record being updated. It is `None` for a new record. Child rows are checked against it.
	"""
	if not data:
		raise ToolDenied("invalid_arguments", _("data must name at least one field.", context=CONTEXT))
	can_write = fields.writable(meta)
	for key, value in data.items():
		if key == "name" and allow_name and meta.autoname == "prompt":
			continue
		field = meta.get_field(key)
		if key in RESERVED_KEYS or key == "name" or field is None:
			raise ToolDenied("invalid_arguments", _("Field {0} cannot be set.", context=CONTEXT).format(key))
		if policy.is_secret_field(field):
			raise ToolDenied(
				"secret_field", _("Field {0} is secret. A human enters it.", context=CONTEXT).format(key)
			)
		if key not in can_write:
			raise ToolDenied(
				"field_not_permitted", _("You may not write field {0}.", context=CONTEXT).format(key)
			)
		if field.fieldtype in ("Table", "Table MultiSelect"):
			_check_rows(meta, field, value, doc)


def _check_rows(meta, field, rows: Any, doc) -> None:
	"""Checks the child table rows.

	Frappe updates a row by its name only and writes the parent record to the row itself
	(`_init_child` and `update_child_table` in `frappe/model/document.py`). Therefore:

	- A row name can only be the name of a row in this table of this parent record.
	- For a new record and a new row the name is not taken from the client.
	- Row fields also need field-level write permission. Frappe skips this for a new record.
	"""
	if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
		raise ToolDenied(
			"invalid_arguments", _("Field {0} takes a list of rows.", context=CONTEXT).format(field.fieldname)
		)
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
						_(
							"A row name must be an existing row of this document. New rows carry no name.",
							context=CONTEXT,
						),
					)
				seen.add(name)
				continue
			child_field = child_meta.get_field(key)
			if child_field is None or key in RESERVED_KEYS or key in ROW_RESERVED_KEYS:
				raise ToolDenied(
					"invalid_arguments", _("Row field {0} cannot be set.", context=CONTEXT).format(key)
				)
			if policy.is_secret_field(child_field):
				raise ToolDenied(
					"secret_field", _("Field {0} is secret. A human enters it.", context=CONTEXT).format(key)
				)
			if key not in can_write:
				raise ToolDenied(
					"field_not_permitted", _("You may not write row field {0}.", context=CONTEXT).format(key)
				)
			if child_field.fieldtype in ("Table", "Table MultiSelect"):
				raise ToolDenied(
					"invalid_arguments", _("Rows cannot carry their own tables.", context=CONTEXT)
				)


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
	"""Loads the record and checks the permission.

	Execution passes `expected_version`. The record is then read with a row lock and compared
	with the version in the preview. This way a change made in between is not overwritten.
	"""
	meta = writable_meta(doctype)
	doc = frappe.get_doc(doctype, name, for_update=expected_version is not None)
	doc.check_permission(ptype)
	if expected_version is not None and str(doc.modified) != expected_version:
		raise ToolDenied("document_changed", _("The document changed after the preview.", context=CONTEXT))
	return meta, doc


# --- create ---


def preview_create(doctype: str, data: dict[str, Any]) -> dict:
	meta = writable_meta(doctype)
	if not frappe.has_permission(doctype, "create"):
		raise ToolDenied("permission", _("You may not create {0}.", context=CONTEXT).format(doctype))
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
		raise ToolDenied("permission", _("You may not create {0}.", context=CONTEXT).format(doctype))
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


# --- update ---


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
	"""The old value in the preview. For a child table the readable fields of the rows are shown.

	The submitted row list replaces the whole table. The human must also see the row to be deleted.
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


# --- submit, cancel, delete ---


def _check_submit(meta, doc) -> None:
	if not meta.is_submittable or doc.docstatus != 0:
		raise ToolDenied(
			"invalid_arguments", _("Only a draft of a submittable DocType can be submitted.", context=CONTEXT)
		)


def _check_cancel(doc) -> None:
	if doc.docstatus != 1:
		raise ToolDenied(
			"invalid_arguments", _("Only a submitted document can be cancelled.", context=CONTEXT)
		)


def _check_delete(doc) -> None:
	if doc.docstatus == 1:
		raise ToolDenied(
			"invalid_arguments", _("Cancel a submitted document before deleting it.", context=CONTEXT)
		)


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
