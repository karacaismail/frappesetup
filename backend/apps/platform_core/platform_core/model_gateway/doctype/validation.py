"""Validate the JSON arrays supported by gateway registry records."""

import json

import frappe
from frappe import _


def parse_records(value, label, *, required=False):
	if value is None or value == "":
		value = []
	elif isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, RecursionError):
			value = None

	if not isinstance(value, list) or (required and not value):
		frappe.throw(_("{0} must contain a valid JSON array.").format(_(label)))
	return value


def encode_identifiers(value, label):
	items = parse_records(value, label)
	if any(not isinstance(item, str) or not item or item != item.strip() for item in items):
		frappe.throw(_("{0} must contain only non-empty identifiers.").format(_(label)))
	if len(set(items)) != len(items):
		frappe.throw(_("{0} contains duplicate identifiers.").format(_(label)))
	return json.dumps(items, separators=(",", ":"))
