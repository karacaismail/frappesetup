"""Read tools. They run with the user's identity and Frappe's permission paths (G-85)."""

import re
from itertools import islice
from typing import Annotated, Any

import frappe
from frappe import _
from frappe.mcp.tools import ToolArguments
from pydantic import Field

from platform_core.yapay_zeka import fields as field_rules
from platform_core.yapay_zeka import policy
from platform_core.yapay_zeka.errors import CONTEXT, ToolDenied
from platform_core.yapay_zeka.tools import envelope

# The limits live in `envelope`. They are named here so that a test can lower them for this module.
MAX_CHILD_ROWS = envelope.MAX_CHILD_ROWS
MAX_RESULT_BYTES = envelope.MAX_RESULT_BYTES
# Bytes of the JSON keys and brackets around the columns and rows of a report result.
REPORT_ENVELOPE_BYTES = 32

OPERATORS = frozenset({"=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "between", "is"})
# The order of a list that names none. Newest first, with the name as the tie breaker.
DEFAULT_ORDER = "creation desc, name desc"
ORDER_BY = re.compile(r"^\s*(\w+)(?:\s+(asc|desc))?\s*$", re.IGNORECASE)


class ListDocumentsArguments(ToolArguments):
	doctype: str = Field(min_length=1, max_length=140)
	filters: dict[str, Any] | None = None
	fields: list[Annotated[str, Field(max_length=140)]] | None = Field(default=None, max_length=100)
	order_by: str | None = Field(default=None, max_length=140)
	start: int = Field(default=0, ge=0)
	limit: int = Field(default=20, ge=1, le=100)


class GetDocumentArguments(ToolArguments):
	doctype: str = Field(min_length=1, max_length=140)
	name: str = Field(min_length=1, max_length=140)


class RunReportArguments(ToolArguments):
	report: str = Field(min_length=1, max_length=140)
	filters: dict[str, Any] | None = None
	limit: int = Field(default=100, ge=1, le=500)


def readable_meta(doctype: str):
	"""Returns the definition if the DocType is readable. Otherwise it denies the call."""
	meta = field_rules.get_meta(doctype)
	if doctype in policy.READ_BLOCKED:
		raise ToolDenied(
			"blocked_doctype", _("DocType {0} is closed to AI tools.", context=CONTEXT).format(doctype)
		)
	if meta.istable:
		raise ToolDenied(
			"invalid_arguments", _("Read child rows through their parent document.", context=CONTEXT)
		)
	if not frappe.has_permission(doctype, "read"):
		raise ToolDenied("permission", _("You may not read DocType {0}.", context=CONTEXT).format(doctype))
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

	order = DEFAULT_ORDER
	if order_by:
		match = ORDER_BY.match(order_by)
		if not match:
			raise ToolDenied(
				"invalid_arguments", _("order_by takes a field name and asc or desc.", context=CONTEXT)
			)
		field_rules.check_readable(meta, match.group(1))
		field, direction = match.group(1), (match.group(2) or "asc").lower()
		# The name breaks ties. Without it rows with equal values can repeat or drop out between pages.
		order = f"{field} {direction}" if field == "name" else f"{field} {direction}, name {direction}"

	# `frappe.get_list` applies user permissions and sharing (G-3).
	rows = frappe.get_list(
		doctype,
		fields=wanted,
		filters=query_filters,
		order_by=order,
		limit_start=start,
		limit_page_length=limit + 1,
	)
	page = rows[:limit]
	documents, cut = envelope.fit_rows(page, MAX_RESULT_BYTES)
	if cut and not documents:
		# The first document alone is over the byte limit. It is returned cut, so that the
		# caller always moves forward and never gets the same empty page again.
		documents = [envelope.fit_document(dict(page[0]), MAX_RESULT_BYTES)[0]]
	more = len(documents) < len(page) or len(rows) > limit
	result = {
		"documents": documents,
		"has_next_page": more,
		"next_start": start + len(documents) if more else None,
		"truncated": cut,
	}
	return envelope.stamp(result, f"DocType: {doctype}")


def get_document(doctype: str, name: str) -> dict:
	meta = readable_meta(doctype)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()
	document, cut = envelope.fit_document(field_rules.clean(doc.as_dict(), meta), MAX_RESULT_BYTES)
	return envelope.stamp({"document": document, "truncated": cut}, f"DocType: {doctype}")


def run_report(report: str, filters: dict[str, Any] | None = None, limit: int = 100) -> dict:
	from frappe.desk.query_report import run

	report_doc = frappe.get_doc("Report", report)
	if report_doc.ref_doctype in policy.READ_BLOCKED:
		raise ToolDenied(
			"blocked_doctype", _("This report reads a DocType that is closed to AI tools.", context=CONTEXT)
		)
	if not report_doc.is_permitted() or not frappe.has_permission(report_doc.ref_doctype, "report"):
		raise ToolDenied("permission", _("You may not run report {0}.", context=CONTEXT).format(report))

	# A query report reads with its own SQL and skips the list hook of the access engine.
	# The access engine's report gate decides whether this user may get the report's data.
	guard = _report_guard()
	if guard is None:
		raise ToolDenied(
			"report_gate_unavailable",
			_("Reports are closed until the access engine's report gate is installed.", context=CONTEXT),
		)
	guard(report)
	if report_doc.prepared_report:
		# Frappe prepares such a report in the background because its result is large. The report
		# function returns the whole result at once, so the layer cannot cap it inside the request.
		raise ToolDenied(
			"report_too_large", _("Report {0} is prepared in the background.", context=CONTEXT).format(report)
		)
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
	# The limit covers columns and rows together. Rows without their columns would be useless,
	# so columns that do not fit leave the result empty.
	budget = MAX_RESULT_BYTES - envelope.size(columns) - REPORT_ENVELOPE_BYTES
	if budget <= 0:
		columns, rows, cut = [], [], True
	else:
		rows, cut = envelope.fit_rows(rows, budget)
	result = {"columns": columns, "rows": rows, "truncated": truncated or cut}
	return envelope.stamp(result, f"Report: {report}")


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
	"""Returns the column's field name, type and label. The text form is `Label:Type/Options:Width`."""
	if isinstance(column, dict):
		label = str(column.get("label") or "")
		return str(column.get("fieldname") or frappe.scrub(label)), str(column.get("fieldtype") or ""), label
	parts = str(column).split(":")
	fieldtype = parts[1].split("/")[0] if len(parts) > 1 else ""
	return frappe.scrub(parts[0]), fieldtype, parts[0]


def _secret_column(source, fieldname: str, fieldtype: str, label: str) -> bool:
	"""A report column does not go to the model in these cases (report contract):

	- the column type is a secret type, for example "Password",
	- the field name or label matches the secret name pattern,
	- the field with the same name in the report's source DocType is secret.

	The report author must mark a secret value from another source in one of these three ways.
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
			raise ToolDenied(
				"invalid_arguments", _("A filter is a value or an [operator, value] pair.", context=CONTEXT)
			)
		return [str(condition[0]).lower(), condition[1]]
	if isinstance(condition, dict):
		raise ToolDenied(
			"invalid_arguments", _("A filter is a value or an [operator, value] pair.", context=CONTEXT)
		)
	return condition
