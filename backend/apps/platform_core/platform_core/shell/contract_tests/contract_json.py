"""Read JSON-subset OpenAPI, schema fixtures, and responses without coercion."""

import json
import math


def _unique_object(pairs):
	result = {}
	for key, value in pairs:
		if key in result:
			raise ValueError(f"Duplicate JSON key: {key}")
		result[key] = value
	return result


def _reject_constant(constant: str) -> None:
	raise ValueError(f"Nonfinite JSON number: {constant}")


def _finite_float(value: str) -> float:
	number = float(value)
	if not math.isfinite(number):
		_reject_constant(value)
	return number


def parse_json(source: str | bytes):
	return json.loads(
		source, object_pairs_hook=_unique_object, parse_constant=_reject_constant, parse_float=_finite_float
	)
