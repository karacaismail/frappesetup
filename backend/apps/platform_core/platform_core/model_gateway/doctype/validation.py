"""Validate gateway registry field formats."""

import json
from urllib.parse import urlsplit

import frappe
from frappe import _


def _label(label, doctype):
	# Frappe stores DocType field labels under the DocType name as context.
	return _(label, context=doctype)


def parse_records(value, label, doctype, *, required=False):
	if value is None or value == "":
		value = []
	elif isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, RecursionError):
			value = None

	if not isinstance(value, list) or (required and not value):
		frappe.throw(_("{0} must contain a valid JSON array.").format(_label(label, doctype)))
	return value


def encode_identifiers(value, label, doctype):
	items = parse_records(value, label, doctype)
	if any(not isinstance(item, str) or not item or item != item.strip() for item in items):
		frappe.throw(_("{0} must contain only non-empty identifiers.").format(_label(label, doctype)))
	if len(set(items)) != len(items):
		frappe.throw(_("{0} contains duplicate identifiers.").format(_label(label, doctype)))
	return json.dumps(items, separators=(",", ":"))


def is_valid_url(value, *, https_only=False):
	"""Return whether a non-empty address passes the registry URL rules. Writes no message."""
	schemes = {"https"} if https_only else {"http", "https"}
	if not isinstance(value, str) or any(
		character.isspace() or ord(character) < 32 or character in "?#\\" for character in value
	):
		return False
	try:
		url = urlsplit(value)
		port = url.port
	except ValueError:
		return False
	return bool(url.scheme in schemes and url.hostname and url.username is None and port != 0)


def validate_url(value, label, doctype, *, https_only=False):
	if not value or is_valid_url(value, https_only=https_only):
		return
	if https_only:
		frappe.throw(
			_("{0} must be an HTTPS address without credentials, a query, or a fragment.").format(
				_label(label, doctype)
			)
		)
	frappe.throw(
		_("{0} must be an HTTP or HTTPS address without credentials, a query, or a fragment.").format(
			_label(label, doctype)
		)
	)
