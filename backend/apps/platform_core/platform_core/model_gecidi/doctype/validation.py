"""Validate gateway registry field formats."""

import json
from urllib.parse import urlsplit

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


def validate_url(value, label, *, https_only=False):
	if not value:
		return
	schemes = {"https"} if https_only else {"http", "https"}
	if isinstance(value, str) and not any(
		character.isspace() or ord(character) < 32 or character in "?#\\" for character in value
	):
		try:
			url = urlsplit(value)
			port = url.port
		except ValueError:
			pass
		else:
			if url.scheme in schemes and url.hostname and url.username is None and port != 0:
				return
	if https_only:
		frappe.throw(
			_("{0} must be an HTTPS address without credentials, a query, or a fragment.").format(_(label))
		)
	frappe.throw(
		_("{0} must be an HTTP or HTTPS address without credentials, a query, or a fragment.").format(
			_(label)
		)
	)
