"""Translate the supported Frappe condition subset without evaluating source."""

import json
import math
import re

FIELD_NAME = re.compile(r"[A-Za-z_]\w*", re.ASCII)
PREDICATE = re.compile(
	r"(?P<negated>!)?\s*(?P<scope>doc|parent)\.(?P<field>[A-Za-z_]\w*)"
	r"(?:\s*(?P<operator>===|!==|>=|<=|>|<)\s*(?P<literal>.+))?",
	re.ASCII,
)
SINGLE_QUOTED = re.compile(r"'([^'\\\r\n]*)'")
OPERATORS = {"===": "eq", "!==": "ne", ">=": "gte", "<=": "lte", ">": "gt", "<": "lt"}


def project_condition(source: object, readable: set[str], parent_readable: set[str] | None) -> dict | None:
	if not isinstance(source, str):
		return None
	source = source.strip()
	if FIELD_NAME.fullmatch(source) and source in readable:
		return {"scope": "doc", "field": source, "op": "truthy"}
	if not source.startswith("eval:"):
		return None
	match = PREDICATE.fullmatch(source[5:].strip())
	if not match:
		return None
	scope, field, operator, literal, negated = match.group("scope", "field", "operator", "literal", "negated")
	allowed = readable if scope == "doc" else parent_readable
	if not allowed or field not in allowed:
		return None
	if operator is None:
		return {"scope": scope, "field": field, "op": "falsy" if negated else "truthy"}
	if negated:
		return None
	single = SINGLE_QUOTED.fullmatch(literal)
	try:
		value = single[1] if single else json.loads(literal)
	except (ValueError, RecursionError):
		return None
	if isinstance(value, (list, dict)) or (isinstance(value, float) and not math.isfinite(value)):
		return None
	return {"scope": scope, "field": field, "op": OPERATORS[operator], "value": value}
