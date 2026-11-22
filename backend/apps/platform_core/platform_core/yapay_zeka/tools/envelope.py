"""What every read result carries besides its data: when, where, from what, and whether it was cut."""

import json
from typing import Any

import frappe
from frappe.utils.response import json_handler

from platform_core.yapay_zeka import timestamps

# One child table of a document returns at most this many rows.
MAX_CHILD_ROWS = 200
# The data of one read result is at most this many bytes of JSON.
MAX_RESULT_BYTES = 262_144
# A single text value longer than this is cut when a document is over the byte limit.
MAX_TEXT_CHARS = 20_000


def stamp(result: dict, source: str) -> dict:
	"""Add the time of the read, the site and the source of the data."""
	return {**result, "as_of": timestamps.now_iso(), "site": frappe.local.site, "source": source}


def size(value: Any) -> int:
	"""Bytes of the value as JSON, the way it leaves the layer."""
	return len(json.dumps(value, default=json_handler, ensure_ascii=False).encode())


def fit_rows(rows, limit_bytes: int) -> tuple[list, bool]:
	"""Keep rows while they fit into the byte limit. Return the kept rows and whether any were left out."""
	kept, used = [], 2
	for row in rows:
		used += size(row) + 2
		if used > limit_bytes:
			return kept, True
		kept.append(row)
	return kept, False


def fit_document(document: dict, limit_bytes: int) -> tuple[dict, bool]:
	"""Cut a document down to the row and byte limits. Return it and whether anything was cut."""
	cut = False
	for key, value in document.items():
		if isinstance(value, list) and len(value) > MAX_CHILD_ROWS:
			document[key], cut = value[:MAX_CHILD_ROWS], True
	if size(document) <= limit_bytes:
		return document, cut

	# Over the byte limit: first shorten very long texts, then drop the largest values.
	for key, value in document.items():
		if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
			document[key] = value[:MAX_TEXT_CHARS]
	keep = {"name", "doctype"}
	while size(document) > limit_bytes:
		largest = max(
			(key for key in document if key not in keep), key=lambda key: size(document[key]), default=None
		)
		if largest is None:
			break
		del document[largest]
	return document, True
