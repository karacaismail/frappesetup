"""Bounded read of server-side identity links for identity-sync reconciliation."""

import re

import frappe
from frappe import _

from platform_core.kimlik import provisioning
from platform_core.kimlik.exceptions import InvalidInput

MAX_START = 2**63 - 1
MAX_PAGE_LENGTH = 500


def list_linked_identities(start: object, page_length: object) -> dict:
	offset = _integer(start, "start", 0, MAX_START)
	limit = _integer(page_length, "page_length", 1, MAX_PAGE_LENGTH)
	link = frappe.qb.DocType(provisioning.LINK)
	user = frappe.qb.DocType("User")
	# The service authorization has already run. This single query projects only the contract fields.
	rows = (
		frappe.qb.from_(link)
		.inner_join(user)
		.on(link.user == user.name)
		.select(link.issuer, link.subject, user.enabled)
		.orderby(link.subject, link.issuer)
		.offset(offset)
		.limit(limit + 1)
		.run(as_dict=True)
	)
	return {
		"identities": [
			{"issuer": row.issuer, "subject": row.subject, "enabled": bool(row.enabled)}
			for row in rows[:limit]
		],
		"has_next_page": len(rows) > limit,
	}


def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
	if isinstance(value, str) and re.fullmatch(r"[0-9]{1,19}", value):
		value = int(value)
	if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
		frappe.throw(
			_("Field {0} must be an integer from {1} to {2}.", context="platform_core.kimlik").format(
				field, minimum, maximum
			),
			InvalidInput,
		)
	return value
