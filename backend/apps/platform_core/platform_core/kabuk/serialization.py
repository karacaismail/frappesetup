"""Pure projections: never mutate Frappe's shared metadata objects."""

import json
from copy import deepcopy
from hashlib import sha256

from platform_core.kabuk.conditions import project_condition

FIELD_PROPERTIES = (
	"fieldname",
	"fieldtype",
	"label",
	"description",
	"options",
	"default",
	"reqd",
	"read_only",
	"hidden",
	"permlevel",
	"depends_on",
	"mandatory_depends_on",
	"read_only_depends_on",
	"fetch_from",
	"fetch_if_empty",
	"set_only_once",
	"unique",
	"in_list_view",
	"in_standard_filter",
	"precision",
	"length",
	"non_negative",
	"collapsible",
	"collapsible_depends_on",
)


BOOLEAN_PROPERTIES = {
	"reqd",
	"hidden",
	"fetch_if_empty",
	"set_only_once",
	"unique",
	"in_list_view",
	"in_standard_filter",
	"non_negative",
	"collapsible",
}
STRING_PROPERTIES = {"label", "description", "options", "default", "fetch_from", "precision"}


DEPENDENCY_PROPERTIES = (
	"depends_on",
	"mandatory_depends_on",
	"read_only_depends_on",
	"collapsible_depends_on",
)


def digest(value: object) -> str:
	"""Hash stable JSON while retaining list order and scalar values."""
	encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str)
	return sha256(encoded.encode("utf-8")).hexdigest()


def project_meta(
	schema: dict, readable: set[str], writable: set[str], *, parent_readable: set[str] | None = None
) -> dict:
	"""Return only UI properties and readable fields, without permission rows."""
	fields = []
	for source in schema.get("fields", []):
		name = source.get("fieldname")
		if name not in readable:
			continue
		field = {key: deepcopy(source[key]) for key in FIELD_PROPERTIES if key in source}
		unsupported = []
		for key in DEPENDENCY_PROPERTIES:
			source_condition = field.pop(key, None)
			if not source_condition:
				continue
			condition = project_condition(source_condition, readable, parent_readable)
			if condition is None:
				unsupported.append(key)
			else:
				field[key] = condition
		if unsupported:
			field["unsupported_conditions"] = unsupported
		fetch_from = field.get("fetch_from")
		if fetch_from and fetch_from.partition(".")[0] not in readable:
			field.pop("fetch_from")
			field.pop("fetch_if_empty", None)
		if field["fieldtype"] == "Dynamic Link" and field.get("options") not in readable:
			field.pop("options", None)
		for key in field.keys() & BOOLEAN_PROPERTIES:
			field[key] = field[key] in (True, 1, "1")
		for key in field.keys() & STRING_PROPERTIES:
			if field[key] is not None and not isinstance(field[key], str):
				field[key] = str(field[key])
		field["read_only"] = (
			source.get("read_only") in (True, 1, "1")
			or name not in writable
			or "read_only_depends_on" in unsupported
		)
		# A configured password default must never become client bootstrap data.
		if field.get("fieldtype") == "Password":
			field.pop("default", None)
		fields.append(field)
	return {
		"name": schema["name"],
		"module": schema.get("module"),
		"fields": fields,
		"title_field": schema.get("title_field") if schema.get("title_field") in readable else None,
		"search_fields": ",".join(
			name.strip()
			for name in (schema.get("search_fields") or "").split(",")
			if name.strip() in readable
		),
		"sort_field": schema.get("sort_field") if schema.get("sort_field") in readable else None,
	}


def etag_for(site: str, user: str, version: str, payload: object) -> str:
	"""Scope even identical visible schemas to the current security principal."""
	return '"' + digest([site, user, version, payload]) + '"'


def matches_etag(header: str | None, etag: str) -> bool:
	"""Apply weak comparison for conditional GET using opaque quoted validators."""
	if not header:
		return False
	for candidate in header.split(","):
		candidate = candidate.strip()
		if candidate == "*":
			return True
		if candidate.startswith("W/"):
			candidate = candidate[2:]
		if candidate == etag:
			return True
	return False
