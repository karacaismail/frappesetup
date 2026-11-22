"""Okuma araçları. Kullanıcının kimliğiyle ve Frappe'nin izin yollarıyla çalışır (G-85)."""

import re
from itertools import islice
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

	# A query report reads with its own SQL and skips the list hook of the access engine.
	# The access engine's report gate decides whether this user may get the report's data.
	guard = _report_guard()
	if guard is None:
		raise ToolDenied(
			"report_gate_unavailable",
			_("Reports are closed until the access engine's report gate is installed."),
		)
	guard(report)
	if report_doc.prepared_report:
		# Frappe prepares such a report in the background because its result is large. The report
		# function returns the whole result at once, so the layer cannot cap it inside the request.
		raise ToolDenied("report_too_large", _("Report {0} is prepared in the background.").format(report))
	data = run(report_name=report, filters=filters or {})
	source = field_rules.get_meta(report_doc.ref_doctype)
	columns, keep = [], []
	for index, column in enumerate(data.get("columns") or []):
		fieldname, fieldtype, label = _column(column)
		if not _secret_column(source, fieldname, fieldtype, label):
			keep.append((index, fieldname))
			columns.append(column)

	# Only `limit` rows are read and copied. One more row is read to learn whether more exist.
	rows, truncated = [], False
	for row in islice(data.get("result") or [], limit + 1):
		if len(rows) == limit:
			truncated = True
			break
		if isinstance(row, dict):
			rows.append({name: row.get(name) for _index, name in keep if name in row})
		elif isinstance(row, list | tuple):
			rows.append([row[index] for index, _name in keep if index < len(row)])
	return {"columns": columns, "rows": rows, "truncated": truncated}


def _report_guard():
	"""Return the access engine's report gate, or None while it is not installed.

	The gate is `platform_core.erisim.api.report_guard`, the public path of that module.
	The report tool stays closed without it. That is the safe default.
	"""
	try:
		from platform_core.erisim.api import report_guard
	except ImportError:
		# Either the module or the function is not there yet.
		return None
	return report_guard


def _column(column: Any) -> tuple[str, str, str]:
	"""Sütunun alan adını, türünü ve etiketini döner. Metin biçimi `Etiket:Tür/Seçenek:Genişlik` olur."""
	if isinstance(column, dict):
		label = str(column.get("label") or "")
		return str(column.get("fieldname") or frappe.scrub(label)), str(column.get("fieldtype") or ""), label
	parts = str(column).split(":")
	fieldtype = parts[1].split("/")[0] if len(parts) > 1 else ""
	return frappe.scrub(parts[0]), fieldtype, parts[0]


def _secret_column(source, fieldname: str, fieldtype: str, label: str) -> bool:
	"""Rapor sütunu şu durumlarda modele gitmez (rapor sözleşmesi):

	- sütunun türü gizli türdür, örneğin “Password”,
	- alan adı ya da etiketi gizli ad kalıbına uyar,
	- raporun kaynak DocType'ında aynı adlı alan gizlidir.

	Raporu yazan, başka kaynaktan gelen gizli değeri bu üç yoldan biriyle işaretlemelidir.
	"""
	if fieldtype.strip() in policy.SECRET_FIELDTYPES:
		return True
	if policy.is_secret_fieldname(frappe.scrub(fieldname)) or policy.is_secret_fieldname(frappe.scrub(label)):
		return True
	field = source.get_field(fieldname)
	return field is not None and policy.is_secret_field(field)


def _condition(condition: Any) -> Any:
	if isinstance(condition, list):
		if len(condition) != 2 or str(condition[0]).lower() not in OPERATORS:
			raise ToolDenied("invalid_arguments", _("A filter is a value or an [operator, value] pair."))
		return [str(condition[0]).lower(), condition[1]]
	if isinstance(condition, dict):
		raise ToolDenied("invalid_arguments", _("A filter is a value or an [operator, value] pair."))
	return condition
