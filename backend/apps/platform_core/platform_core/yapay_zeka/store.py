"""The only place that writes the layer's own records.

`ignore_permissions` and direct database reads exist only in this file (G-4).
Reason: "AI Action Log" and "AI Action Proposal" are system records. The end user has no
permission on these types. The user does not choose the target record. Rows returned to
the user are filtered here by the `user` field. A test checks that this exception does not
spread to another file.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime

LOG = "AI Action Log"
PROPOSAL = "AI Action Proposal"


@contextmanager
def _as_system(doc: Document) -> Iterator[Document]:
	"""Write one of the layer's own records without the user's permission, for this write only.

	The flag stays on the document object otherwise and would skip later permission checks (G-4).
	It is put back in `finally`, also when the write fails.
	"""
	previous = doc.flags.ignore_permissions
	doc.flags.ignore_permissions = True  # nosemgrep: frappe-ignore-permissions
	try:
		yield doc
	finally:
		doc.flags.ignore_permissions = previous


def insert_log(values: dict) -> str:
	with _as_system(frappe.get_doc({"doctype": LOG, **values})) as doc:
		doc.insert()
	return doc.name


def insert_proposal(values: dict) -> Document:
	with _as_system(frappe.get_doc({"doctype": PROPOSAL, **values})) as doc:
		doc.insert()
	return doc


def load_proposal(name: str, *, for_update: bool = False) -> Document | None:
	if not isinstance(name, str) or not frappe.db.exists(PROPOSAL, name):
		return None
	return frappe.get_doc(PROPOSAL, name, for_update=for_update)


def save_proposal(doc: Document) -> None:
	with _as_system(doc):
		doc.save()


PROPOSAL_LIST_FIELDS = (
	"name",
	"creation",
	"status",
	"result",
	"tool",
	"target_doctype",
	"target_name",
	"destructive",
	"billable",
	"preview_json",
	"digest",
	"expires_at",
	"result_document",
	"error",
)


def proposals_of(user: str, status: str | None, start: int, limit: int) -> list[dict]:
	"""Return the user's proposals in one bounded query, newest first.

	A pending proposal past its time counts as expired, so the time is part of the query.
	"""
	filters: dict = {"user": user}
	or_filters = None
	now = now_datetime()
	if status == "pending":
		filters.update(status="pending", expires_at=(">=", now))
	elif status == "expired":
		filters["status"] = ("in", ("pending", "expired"))
		or_filters = [["status", "=", "expired"], ["expires_at", "<", now]]
	elif status:
		filters["status"] = status
	return frappe.get_all(
		PROPOSAL,
		filters=filters,
		or_filters=or_filters,
		fields=list(PROPOSAL_LIST_FIELDS),
		order_by="creation desc, name desc",
		limit_start=start,
		limit=limit,
	)


def unresolved_unknown_exists(target_key: str, *, exclude: str | None = None) -> bool:
	"""Is there an execution with an unknown result on the same target?"""
	filters = {"target_key": target_key, "status": "consumed", "result": "unknown"}
	if exclude:
		filters["name"] = ("!=", exclude)
	return bool(frappe.db.exists(PROPOSAL, filters))


def lock_target(target_key: str) -> list[dict]:
	"""Read all proposals of the same target with a row lock.

	If two approvals race on the same target, the second waits here. When the `unknown` write
	of the first is committed, the second sees it. The lock is in the database, so it also
	works across several servers.
	"""
	return frappe.db.get_values(
		PROPOSAL, {"target_key": target_key}, ["name", "status", "result"], for_update=True, as_dict=True
	)


def lock_row(doctype: str, name: str) -> bool:
	"""Lock the row of a system record. Return false if the row does not exist.

	Admin tools lock the real target with this just before they write it. No value is read.
	"""
	return bool(frappe.db.get_value(doctype, name, "name", for_update=True))


def row_stamp(doctype: str, name: str) -> str | None:
	"""The `modified` value of a target row, read by the layer itself. None if the row does not exist."""
	value = frappe.db.get_value(doctype, name, "modified")
	return str(value) if value else None


def locked_row_stamp(doctype: str, name: str) -> str | None:
	"""Lock a target row and return its `modified` value from that same locking read.

	A locking read returns the latest committed row even under repeatable read. An unlocked
	read after the lock could still answer from the older snapshot of the transaction.
	"""
	value = frappe.db.get_value(doctype, name, "modified", for_update=True)
	return str(value) if value else None


def latest_version(doctype: str | None, name: str | None) -> str | None:
	"""Name of the "Version" record the write produced. Written only as a link in the log."""
	if not doctype or not name:
		return None
	return frappe.db.get_value(
		"Version", {"ref_doctype": doctype, "docname": name}, "name", order_by="creation desc"
	)


def purge_older_than(days: int, *, delete: bool) -> tuple[int, int]:
	"""Count the records past the retention period and delete them if asked.

	The delete is done directly in the database. The controller of the log blocks deleting
	rows one by one. Only `retention.purge` calls this path. That function checks the admin role.
	"""
	cutoff = add_days(now_datetime(), -days)
	log_filters = {"creation": ("<", cutoff)}
	proposal_filters = {"creation": ("<", cutoff)}
	unresolved = frappe.get_all(PROPOSAL, filters={"status": "consumed", "result": "unknown"}, pluck="name")
	if unresolved:
		proposal_filters["name"] = ("not in", unresolved)
	counts = frappe.db.count(LOG, log_filters), frappe.db.count(PROPOSAL, proposal_filters)
	if delete:
		frappe.db.delete(LOG, log_filters)
		frappe.db.delete(PROPOSAL, proposal_filters)
	return counts
