"""A small JSON Schema check for the shapes this layer publishes.

It covers the keywords the layer's own schemas use: `type`, `enum`, `required`, `properties`
and `items`. The layer checks a preview with it before the preview is stored.
"""

from typing import Any

TYPES = {
	"object": dict,
	"array": list,
	"string": str,
	"boolean": bool,
	"integer": int,
	"null": type(None),
}


def problems(value: Any, schema: dict, path: str = "value") -> list[str]:
	"""Return what is wrong with `value` under `schema`. An empty list means it fits."""
	found = []
	kinds = schema.get("type")
	if kinds:
		kinds = [kinds] if isinstance(kinds, str) else kinds
		bool_as_number = isinstance(value, bool) and "boolean" not in kinds
		if bool_as_number or not isinstance(value, tuple(TYPES[kind] for kind in kinds)):
			return [f"{path} must be {' or '.join(kinds)}"]
	if "enum" in schema and value not in schema["enum"]:
		found.append(f"{path} is not an allowed value")
	if isinstance(value, dict):
		found += [f"{path}.{key} is missing" for key in schema.get("required", []) if key not in value]
		for key, child in schema.get("properties", {}).items():
			if key in value:
				found += problems(value[key], child, f"{path}.{key}")
	if isinstance(value, list) and "items" in schema:
		for index, item in enumerate(value):
			found += problems(item, schema["items"], f"{path}[{index}]")
	return found
