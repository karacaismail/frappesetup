"""Insertion for server-owned mobile records."""

import frappe

INTERNAL_TYPES = frozenset(
	{
		"Mobile Sequence",
		"Mobile Account State",
		"Mobile Installation",
		"Mobile Revoked Session",
		"Mobile Operation",
		"Mobile Change",
		"Mobile Delivery",
	}
)


def insert_metadata(doctype, *, ignore_duplicate=False, **fields):
	if doctype not in INTERNAL_TYPES:
		raise ValueError("Only mobile metadata may be inserted here")
	doc = frappe.get_doc({"doctype": doctype, **fields})
	previous = doc.flags.ignore_permissions
	try:
		# The approved operation creates server-owned metadata, never a business record.
		return doc.insert(  # nosemgrep: frappe-ignore-permissions
			ignore_permissions=True, ignore_if_duplicate=ignore_duplicate
		)
	finally:
		doc.flags.ignore_permissions = previous
