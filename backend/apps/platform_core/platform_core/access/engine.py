"""Turns a rule into an SQL condition and decides on a single record with the same condition.

The list and the single record use the same condition. New values are also tested in the database:
the values replace the columns in the same condition. Decision note, sections 5, 6 and 7.
"""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import frappe
from pypika import Case
from pypika.terms import Criterion, Term, ValueWrapper

from platform_core.access import rules
from platform_core.access.subject import DEPARTMENT, EMPLOYEE, department_range, subject, variable

Column = Callable[[str], Term]


def never() -> Criterion:
	return ValueWrapper(1) == ValueWrapper(0)


def always() -> Criterion:
	return ValueWrapper(1) == ValueWrapper(1)


def table_column(doctype: str) -> Column:
	table = frappe.qb.DocType(doctype)
	return lambda fieldname: table[fieldname]


def value_column(doc) -> Column:
	"""Puts the new value of the record in place of the column.

	The value comes from the client. A number is turned into text: MariaDB counts the comparison
	`0 = 'HR-EMP-1'` as true. A list and a dict become an empty value. An empty value meets no condition.
	"""

	def column(fieldname: str) -> Term:
		value = doc.get(fieldname)
		if value is None or isinstance(value, str):
			return ValueWrapper(value)
		if isinstance(value, bool | int | float | Decimal | date | timedelta):
			return ValueWrapper(str(value))
		return ValueWrapper(None)

	return column


def _employees(where: Criterion, kind: str):
	"""Names or users of the employees that match the condition. Used as a subquery."""
	employee = frappe.qb.DocType(EMPLOYEE)
	if kind == "user":
		return frappe.qb.from_(employee).select(employee.user_id).where(where & employee.user_id.isnotnull())
	return frappe.qb.from_(employee).select(employee.name).where(where)


def scope_criterion(rule: dict, doctype: str, values: dict, col: Column) -> Criterion:
	scope = rule["scope"]
	if scope == "all":
		return always()
	kind = rules.match_kind(doctype, rule["match_field"])
	if kind not in rules.SCOPE_KINDS.get(scope, ()):
		# The field may have been deleted or changed later. The rule selects no record.
		return never()
	field = col(rule["match_field"])
	employee = frappe.qb.DocType(EMPLOYEE)

	if scope == "own":
		own = values["user"] if kind == "user" else values["employee"]
		return field == own if own else never()

	if scope == "team":
		if values["employee"] is None:
			return never()
		team = (employee.lft >= values["lft"]) & (employee.rgt <= values["rgt"])
		return field.isin(_employees(team, kind))

	if scope == "department":
		limits = department_range(values["department"])
		if not limits:
			return never()
		department = frappe.qb.DocType(DEPARTMENT)
		departments = (
			frappe.qb.from_(department)
			.select(department.name)
			.where((department.lft >= limits[0]) & (department.rgt <= limits[1]))
		)
		if kind == "department":
			return field.isin(departments)
		return field.isin(_employees(employee.department.isin(departments), kind))

	if scope == "company":
		if not values["company"]:
			return never()
		if kind == "company":
			return field == values["company"]
		return field.isin(_employees(employee.company == values["company"], kind))

	return never()


def filter_criterion(row: list, values: dict, col: Column) -> Criterion:
	fieldname, operator, value = row
	field = col(fieldname)
	if operator == "in":
		return field.isin(value)
	if operator == "not in":
		return field.notin(value)
	if isinstance(value, str) and value in rules.VARIABLES:
		value = variable(value, values)
		if value is None:
			return never()
	return field == value if operator == "=" else field != value


def rule_criterion(rule: dict, doctype: str, values: dict, col: Column) -> Criterion:
	parts = [scope_criterion(rule, doctype, values, col)]
	parts.extend(filter_criterion(row, values, col) for row in rule["filters"])
	return Criterion.all(parts)


def any_rule(applicable: list[dict], doctype: str, user: str, col: Column) -> Criterion:
	values = subject(user)
	return Criterion.any([rule_criterion(rule, doctype, values, col) for rule in applicable])


def list_criterion(doctype: str, user: str) -> Criterion | None:
	"""The list condition. Returns `None` for a document type that is not governed."""
	if not rules.is_governed(doctype):
		return None
	applicable = rules.applicable(doctype, user, "read")
	if not applicable:
		return never()
	return any_rule(applicable, doctype, user, table_column(doctype))


def rule_fields(applicable: list[dict]) -> list[str]:
	"""The fields the rules look at. They are read to see whether they changed."""
	fields = []
	for rule in applicable:
		names = [rule["match_field"]] if rule["scope"] != "all" else []
		names.extend(row[0] for row in rule["filters"])
		fields.extend(name for name in names if name and name not in fields and name != "name")
	return fields


def _flag(criterion: Criterion, alias: str) -> Term:
	return Case().when(criterion, 1).else_(0).as_(alias)


def stored_row(doctype: str, name, flags: dict[str, Criterion], fields: list[str]):
	"""Reads the stored record with one query: the condition results and the fields the rules look at."""
	columns = set(frappe.get_meta(doctype).get_valid_columns())
	table = frappe.qb.DocType(doctype)
	query = frappe.qb.from_(table).select(table.name).where(table.name == name).limit(1)
	for alias, criterion in flags.items():
		query = query.select(_flag(criterion, alias))
	for fieldname in fields:
		if fieldname in columns:
			query = query.select(table[fieldname])
	rows = query.run(as_dict=True)
	return rows[0] if rows else None


def values_match(criterion: Criterion) -> bool:
	"""Tests in the database the condition whose columns are replaced by values."""
	return bool(frappe.qb.select(_flag(criterion, "ok")).run()[0][0])


def decide(doc, ptype: str | None, user: str) -> bool:
	"""The single record decision for a governed document type (decision note, section 6)."""
	doctype = doc.doctype
	operation = rules.operation_of(ptype)
	applicable = rules.applicable(doctype, user, operation)
	if not applicable:
		return False

	if operation != "create" and doc.name:
		fields = rule_fields(applicable)
		criterion = any_rule(applicable, doctype, user, table_column(doctype))
		row = stored_row(doctype, doc.name, {"ok": criterion}, fields)
		if row:
			if not row.ok:
				return False
			if operation not in ("write", "submit"):
				return True
			if all(_same(doc.get(fieldname), row.get(fieldname)) for fieldname in fields):
				return True

	return values_match(any_rule(applicable, doctype, user, value_column(doc)))


def _same(new, stored) -> bool:
	return (new or None) == (stored or None) or str(new) == str(stored)


def decide_stored(doctype: str, name, ptype: str, user: str) -> tuple[bool, list[dict]]:
	"""For the explain endpoint: the decision of the engine on the stored record and the result of each rule."""
	operation = rules.operation_of(ptype)
	all_rules = rules.rules_for(doctype)
	if not all_rules:
		return True, []
	roles = set(frappe.get_roles(user))
	values = subject(user)
	col = table_column(doctype)
	applicable = [rule for rule in all_rules if rules.applies(rule, roles, operation)]
	flags = {
		f"r{position}": rule_criterion(rule, doctype, values, col) for position, rule in enumerate(applicable)
	}
	row = stored_row(doctype, name, flags, []) or {}
	matched = {rule["name"]: bool(row.get(f"r{position}")) for position, rule in enumerate(applicable)}
	report = [
		{
			"name": rule["name"],
			"title": rule["title"],
			"role": rule["role"],
			"scope": rule["scope"],
			"applies": rule["name"] in matched,
			"matches": matched.get(rule["name"], False),
		}
		for rule in all_rules
	]
	return any(matched.values()), report
