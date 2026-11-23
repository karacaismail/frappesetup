"""Read grouped summaries from the same permitted rows as the native document list."""

import json
import math
import re
from typing import Annotated, Literal

import frappe
from frappe.model import get_permitted_fields, numeric_fieldtypes
from frappe.model.document import get_controller
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic import ValidationError as QueryValidationError
from pypika import functions
from pypika.terms import AnalyticFunction

from platform_core.shell.request_policy import FRAMEWORK_PARAMETERS

FIELD_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
FIELD_NAME = Annotated[str, StringConstraints(pattern=FIELD_PATTERN, max_length=140)]
FILTER_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "like", "not like", "in", "not in", "between", "is"}
MAX_GROUPS = 100


class InvalidSummaryQuery(frappe.ValidationError):
	http_status_code = 400


class SummaryQuery(BaseModel):
	model_config = ConfigDict(extra="forbid")

	doctype: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=140)]
	group_by: FIELD_NAME
	aggregate: Literal["sum", "avg"] | None = None
	aggregate_field: FIELD_NAME | None = None
	filters: Annotated[str, StringConstraints(max_length=8192)] | None = None
	limit: int = Field(default=MAX_GROUPS, ge=1, le=MAX_GROUPS)


def invalid_query() -> None:
	frappe.throw(
		frappe._("The collection summary parameters are invalid.", context="shell.collection"),
		InvalidSummaryQuery,
	)


def read_query() -> SummaryQuery:
	request_params = {
		key: argument for key, argument in frappe.form_dict.items() if key not in FRAMEWORK_PARAMETERS
	}
	try:
		query = SummaryQuery.model_validate(request_params)
	except QueryValidationError:
		invalid_query()
	if bool(query.aggregate) != bool(query.aggregate_field):
		invalid_query()
	return query


def filter_rows(raw_filters: str | None, doctype: str) -> list[tuple]:
	if raw_filters is None:
		return []
	try:
		filters = json.loads(raw_filters)
	except ValueError:
		invalid_query()
	if isinstance(filters, dict):
		filters = [
			[fieldname, *operand] if isinstance(operand, list) else [fieldname, "=", operand]
			for fieldname, operand in filters.items()
		]
	if not isinstance(filters, list) or len(filters) > 100:
		invalid_query()

	conditions = []
	for condition in filters:
		if not isinstance(condition, list) or len(condition) not in (3, 4):
			invalid_query()
		if len(condition) == 4 and condition[0] != doctype:
			invalid_query()
		fieldname, operator, operand = condition[-3:]
		if not isinstance(operator, str) or operator.lower() not in FILTER_OPERATORS:
			invalid_query()
		operator = operator.lower()
		operands = operand if isinstance(operand, list) else [operand]
		needs_list = operator in {"in", "not in", "between"}
		if (
			needs_list != isinstance(operand, list)
			or len(operands) > 100
			or (needs_list and not operands)
			or (operator == "between" and len(operands) != 2)
			or (operator == "is" and operand not in ("set", "not set"))
			or any(
				not isinstance(entry, (str, int, float, bool, type(None)))
				or (isinstance(entry, float) and not math.isfinite(entry))
				for entry in operands
			)
		):
			invalid_query()
		conditions.append((fieldname, operator, operand))
	return conditions


def check_fields(meta, user: str, query: SummaryQuery, conditions: list[tuple]) -> None:
	valid_columns = set(meta.get_valid_columns())
	permitted = set(get_permitted_fields(meta.name, user=user, permission_type="read", ignore_virtual=True))
	masked = {field.fieldname for field in meta.get_masked_fields()}
	if user != "Administrator":
		roles = set(frappe.get_roles(user))
		read_levels = {
			permission.permlevel
			for permission in meta.get_permissions()
			if permission.role in roles and permission.read and not permission.if_owner
		}
	else:
		read_levels = None

	requested_fields = [query.group_by, *(item[0] for item in conditions)]
	if query.aggregate_field:
		requested_fields.append(query.aggregate_field)
	for fieldname in requested_fields:
		if (
			not isinstance(fieldname, str)
			or not re.fullmatch(FIELD_PATTERN, fieldname)
			or fieldname not in valid_columns
		):
			invalid_query()
		field = meta.get_field(fieldname)
		if (
			fieldname not in permitted
			or fieldname in masked
			or (field and field.fieldtype == "Password")
			or (field and field.permlevel and read_levels is not None and field.permlevel not in read_levels)
		):
			raise frappe.PermissionError
		if fieldname == query.aggregate_field and (not field or field.fieldtype not in numeric_fieldtypes):
			invalid_query()


def read_summary(query: SummaryQuery, user: str) -> dict:
	if not frappe.db.exists("DocType", query.doctype):
		raise frappe.DoesNotExistError
	meta = frappe.get_meta(query.doctype)
	frappe.has_permission(query.doctype, "read", user=user, throw=True)
	if meta.istable or meta.issingle or meta.is_virtual:
		invalid_query()
	conditions = filter_rows(query.filters, query.doctype)
	check_fields(meta, user, query, conditions)

	fields = list(dict.fromkeys(field for field in (query.group_by, query.aggregate_field) if field))
	permitted_query = frappe.qb.get_query(
		query.doctype, fields=fields, filters=conditions, ignore_permissions=False, user=user
	)
	# Match native list controller restrictions before collecting statistics.
	controller = get_controller(query.doctype)
	if controller_list := getattr(controller, "get_list", None):
		if restricted_query := controller_list(permitted_query):
			permitted_query = restricted_query

	visible_rows = permitted_query.as_("visible_rows")
	grouping_field = visible_rows[query.group_by]
	group_count = functions.Count("*")
	total_count = AnalyticFunction("SUM", group_count).over()
	grouped_query = (
		frappe.qb.from_(visible_rows)
		.select(grouping_field.as_("value"), group_count.as_("count"), total_count.as_("total_count"))
		.groupby(grouping_field)
		.orderby(grouping_field)
		.limit(query.limit + 1)
	)
	if query.aggregate_field:
		operation = functions.Sum if query.aggregate == "sum" else functions.Avg
		grouped_query = grouped_query.select(operation(visible_rows[query.aggregate_field]).as_("aggregate"))

	groups = grouped_query.run(as_dict=True)
	total = int(groups[0]["total_count"]) if groups else 0
	for group in groups:
		group.pop("total_count")
	return {"groups": groups[: query.limit], "total_count": total, "truncated": len(groups) > query.limit}
