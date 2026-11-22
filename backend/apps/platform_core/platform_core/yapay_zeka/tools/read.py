"""Okuma araçları. Kullanıcının kimliğiyle ve Frappe'nin izin yollarıyla çalışır (G-85)."""

import re
from typing import Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from pydantic import Field

from platform_core.yapay_zeka import fields as field_rules
from platform_core.yapay_zeka import policy
from platform_core.yapay_zeka.errors import ToolDenied

OPERATORS = frozenset({"=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is"})
ORDER_BY = re.compile(r"^\s*(\w+)(?:\s+(asc|desc))?\s*$", re.IGNORECASE)


class ListDocumentsArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	filters: dict[str, Any] | None = None
	fields: list[str] | None = None
	order_by: str | None = None
	start: int = Field(default=0, ge=0)
	limit: int = Field(default=20, ge=1, le=100)


class GetDocumentArguments(ToolArguments):
	doctype: str = Field(min_length=1)
	name: str = Field(min_length=1)


class RunReportArguments(ToolArguments):
	report: str = Field(min_length=1)
	filters: dict[str, Any] | None = None
	limit: int = Field(default=100, ge=1, le=500)


def readable_meta(doctype: str):
	"""DocType okunabiliyorsa tanımını döner. Okunamıyorsa çağrıyı reddeder."""
	meta = field_rules.get_meta(doctype)
	if doctype in policy.READ_BLOCKED:
		raise ToolDenied("blocked_doctype", _("DocType {0} is closed to AI tools.").format(doctype))
	if meta.istable:
		raise ToolDenied("invalid_arguments", _("Read child rows through their parent document."))
	if not frappe.has_permission(doctype, "read"):
		raise ToolDenied("permission", _("You may not read DocType {0}.").format(doctype))
	return meta


def list_documents(
	doctype: str,
	filters: dict[str, Any] | None = None,
	fields: list[str] | None = None,
	order_by: str | None = None,
	start: int = 0,
	limit: int = 20,
) -> dict:
	meta = readable_meta(doctype)
	wanted = fields or ["name", *([meta.title_field] if meta.title_field else [])]
	for fieldname in wanted:
		field_rules.check_readable(meta, fieldname)

	query_filters = {}
	for fieldname, condition in (filters or {}).items():
		field_rules.check_readable(meta, fieldname)
		query_filters[fieldname] = _condition(condition)

	order = None
	if order_by:
		match = ORDER_BY.match(order_by)
		if not match:
			raise ToolDenied("invalid_arguments", _("order_by takes a field name and asc or desc."))
		field_rules.check_readable(meta, match.group(1))
		order = f"{match.group(1)} {(match.group(2) or 'asc').lower()}"

	# `frappe.get_list` kullanıcı izinlerini ve paylaşımı uygular (G-3).
	rows = frappe.get_list(
		doctype,
		fields=wanted,
		filters=query_filters,
		order_by=order,
		limit_start=start,
		limit_page_length=limit + 1,
	)
	return {"documents": rows[:limit], "has_next_page": len(rows) > limit}


def get_document(doctype: str, name: str) -> dict:
	meta = readable_meta(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()
	return {"document": field_rules.clean(doc.as_dict(), meta)}


def run_report(report: str, filters: dict[str, Any] | None = None, limit: int = 100) -> dict:
	from frappe.desk.query_report import run

	report_doc = frappe.get_doc("Report", report)
	if report_doc.ref_doctype in policy.READ_BLOCKED:
		raise ToolDenied("blocked_doctype", _("This report reads a DocType that is closed to AI tools."))
	if not report_doc.is_permitted() or not frappe.has_permission(report_doc.ref_doctype, "report"):
		raise ToolDenied("permission", _("You may not run report {0}.").format(report))

	data = run(report_name=report, filters=filters or {}, ignore_prepared_report=True)
	columns, keep = [], []
	for index, column in enumerate(data.get("columns") or []):
		fieldname = column.get("fieldname") if isinstance(column, dict) else str(column).split(":")[0]
		if not policy.is_secret_fieldname(frappe.scrub(fieldname or "")):
			keep.append((index, fieldname))
			columns.append(column)

	rows = []
	for row in (data.get("result") or [])[:limit]:
		if isinstance(row, dict):
			rows.append({name: row.get(name) for _index, name in keep if name in row})
		elif isinstance(row, list | tuple):
			rows.append([row[index] for index, _name in keep if index < len(row)])
	return {"columns": columns, "rows": rows, "truncated": len(data.get("result") or []) > limit}


def _condition(condition: Any) -> Any:
	if isinstance(condition, list):
		if len(condition) != 2 or str(condition[0]).lower() not in OPERATORS:
			raise ToolDenied("invalid_arguments", _("A filter is a value or an [operator, value] pair."))
		return [str(condition[0]).lower(), condition[1]]
	if isinstance(condition, dict):
		raise ToolDenied("invalid_arguments", _("A filter is a value or an [operator, value] pair."))
	return condition
