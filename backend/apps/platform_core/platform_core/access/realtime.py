"""Realtime rooms on governed document types (G-121).

The realtime server lets a socket into a room only after it asks the web process:
`/api/method/frappe.realtime.has_permission` (`frappe/realtime/auth.py:87`).

- The record room gets `doc_update` and `docinfo_update` of one record. Frappe asks with the
  record name. The record hook of the engine runs, so this room already follows the rule.
- The list room gets `list_update` for every record of the type, with the record name and the
  user who changed it (`frappe/model/document.py:1784`). Frappe asks without a record name. The
  record hook does not run then (`frappe/permissions.py:163`), so the role permission alone decides.

A user whom a rule narrows would learn the names of records outside the rule in the list room.
So on a governed document type the list room is open only to a user whose read rules cover
every record. Every other caller gets 403. Their list does not refresh by itself. A manual
refresh still shows the right records, because the list endpoint applies the rule.

`hooks.py` puts `has_permission` below in place of Frappe's endpoint. The address does not change.
"""

import frappe
from frappe import realtime
from frappe.rate_limiter import rate_limit

from platform_core.access import rules


def sees_every_record(doctype: str, user: str) -> bool:
	"""True if a read rule of the user covers every record: scope `all` and no filter."""
	return any(
		rule["scope"] == "all" and not rule["filters"] for rule in rules.applicable(doctype, user, "read")
	)


def list_room_allowed(doctype: str, user: str) -> bool:
	"""Whether the user may receive the `list_update` events of the document type."""
	if user == "Administrator" or not rules.is_governed(doctype):
		return True
	return sees_every_record(doctype, user)


# Guest access and GET as in Frappe's endpoint and its realtime caller (`frappe/realtime/auth.py:87`).
# Frappe's permission check below refuses a guest. The realtime server asks once for each room.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=600, seconds=60, user_based=True)
def has_permission(doctype: str, name: str, ptype: str = "read") -> bool:
	"""Frappe's room check, with the list room closed to a user whom a rule narrows."""
	if not name and not list_room_allowed(doctype, frappe.session.user):
		raise frappe.PermissionError
	return realtime.has_permission(doctype, name, ptype)
