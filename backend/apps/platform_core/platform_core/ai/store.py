"""The only place that writes the layer's own records.

`ignore_permissions` and direct database reads exist only in this file (G-4).
Reason: "AI Action Log" and "AI Action Proposal" are system records. The end user has no
permission on these types. The user does not choose the target record. Rows returned to
the user are filtered here by the `user` field. A test checks that this exception does not
spread to another file.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from time import time

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime

LOG = "PLT AI Action Log"
PROPOSAL = "PLT AI Action Proposal"
MCP_BUDGET = "PLT MCP Call Budget"
MCP_ADMISSION_PREFIX = "mcp_oauth_admitted:"
MCP_BUDGET_RETENTION_SECONDS = 86400


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
	"risk_level",
	"preview_json",
	"digest",
	"expires_at",
	"result_document",
	"error",
)


def proposals_without_risk_level() -> list[dict]:
	"""Proposals opened before the risk level existed (AJA-1001). Only the migration patch reads them."""
	table = frappe.qb.DocType(PROPOSAL)
	return (
		frappe.qb.from_(table)
		.select(table.name, table.tool_class, table.destructive, table.billable)
		.where(table.risk_level.isnull() | (table.risk_level == ""))
		.run(as_dict=True)
	)


def backfill_risk_level(name: str, level: str) -> None:
	"""Write the level of an old proposal. The save path refuses it, because the level is frozen."""
	frappe.db.set_value(PROPOSAL, name, "risk_level", level, update_modified=False)


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


def field_property_rows(doctype: str, fieldname: str, property: str, *, for_update: bool) -> list:
	"""The stored rows behind one field property: "Property Setter" rows, then the field's own rows.

	Each row gives its name, the property's value and `modified`. A standard field is a "DocField"
	row of the DocType, a custom one is a "Custom Field" record. `property` is a known column
	name: the caller checks it against its allow list.

	With `for_update` these are locking reads. They return the latest committed rows and lock
	the gap too, so no other transaction can add the first setter row until this one ends.
	"""
	key = {"doc_type": doctype, "field_name": fieldname, "property": property}
	setters = frappe.db.get_values(
		"Property Setter", key, ["name", "value", "modified"], for_update=for_update, as_dict=True
	)
	found = []
	for table, filters in (
		("DocField", {"parent": doctype, "parenttype": "DocType", "fieldname": fieldname}),
		("Custom Field", {"dt": doctype, "fieldname": fieldname}),
	):
		rows = frappe.db.get_values(table, filters, ["name", property, "modified"], for_update=for_update)
		found += sorted([table, row[0], row[1], str(row[2])] for row in rows)
	return [sorted([row.name, row.value, str(row.modified)] for row in setters), found]


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


def _delete_for_good(doctype: str, name: str) -> None:
	"""Delete one of the layer's own records and keep no copy of it (decision O-32).

	`delete_permanently` stops Frappe from writing a "Deleted Document" copy. `force` skips the
	link check: a log row may still point at the proposal. The log's controller refuses every
	other delete, so the retention flag is set for this one delete only.
	"""
	with _as_system(frappe.get_doc(doctype, name)) as doc:
		doc.flags.retention_purge = True
		doc.delete(force=True, delete_permanently=True)


class SelectionChanged(frappe.ValidationError):
	"""A record chosen for deletion is no longer there. The human saw another set of records."""


def select_expired(days: int, proposal_days: int, batch: int) -> dict:
	"""Choose the records one delete run takes, and count all records past their period.

	A log row is past its period `days` after it was written. A proposal is past it
	`proposal_days` after its decision or its expiry, whichever comes first. Every proposal has
	an expiry, so none stays forever. One run takes at most `batch` records of each kind, oldest
	first.

	`logs` and `proposals` are the names chosen. `logs_waiting` and `proposals_waiting` are all
	records past their period now. Nothing is deleted here.
	"""
	now = now_datetime()
	cutoff = add_days(now, -proposal_days)
	old_logs = {"creation": ("<", add_days(now, -days))}
	# A filter on an empty `decided_at` alone would match every undecided proposal, because the
	# database layer reads an empty date as a very old one. The three groups below do not
	# overlap, so their counts add up.
	groups = (
		[["decided_at", "is", "set"], ["decided_at", "<", cutoff]],
		[["decided_at", "is", "not set"], ["expires_at", "<", cutoff]],
		# Closed late by a human: decided lately, but expired long ago.
		[["decided_at", "is", "set"], ["decided_at", ">=", cutoff], ["expires_at", "<", cutoff]],
	)
	oldest_first = "creation asc, name asc"
	proposals = []
	for filters in groups:
		if len(proposals) < batch:
			proposals += frappe.get_all(
				PROPOSAL, filters=filters, pluck="name", order_by=oldest_first, limit=batch - len(proposals)
			)
	return {
		"logs": frappe.get_all(LOG, filters=old_logs, pluck="name", order_by=oldest_first, limit=batch),
		"logs_waiting": frappe.db.count(LOG, old_logs),
		"proposals": proposals,
		"proposals_waiting": sum(frappe.db.count(PROPOSAL, filters) for filters in groups),
	}


def delete_selected(logs: list[str], proposals: list[str]) -> None:
	"""Delete exactly the chosen records for good. No record is chosen again here.

	Each record is locked first. If one is gone, the set the human saw has changed and nothing
	more is deleted: the caller rolls back and asks for a new preview.
	Only `retention.purge` calls this path. That function checks the admin role.
	"""
	for doctype, names in ((LOG, logs), (PROPOSAL, proposals)):
		for name in names:
			if not frappe.db.get_value(doctype, name, "name", for_update=True):
				raise SelectionChanged
			_delete_for_good(doctype, name)


def charge_mcp_call(name: str, expires_at: int, max_calls: int) -> str | None:
	"""Lock a site counter and keep a separate admission marker in Redis until token expiry."""
	if expires_at <= time():
		return "token_expired"

	table = frappe.qb.DocType(MCP_BUDGET)
	insert = (
		frappe.qb.into(table).columns(table.name, table.calls, table.expires_at).insert(name, 0, expires_at)
	)
	# The no-op update acquires an exclusive lock on MariaDB. A plain duplicate insert may
	# acquire shared locks and deadlock when multiple callers try to upgrade them together.
	if frappe.db.db_type == "postgres":
		insert.on_conflict(table.name).do_nothing().run()
	else:
		insert.on_duplicate_key_update(table.name, table.name).run()

	calls = frappe.db.get_value(MCP_BUDGET, name, "calls", for_update=True)
	now = int(time())
	if expires_at <= now:
		return "token_expired"

	# Write the marker while the database row stays locked. A lost Redis key is repaired using
	# the surviving count. A surviving marker with a fresh database row refuses the token.
	marker = frappe.cache.make_key(MCP_ADMISSION_PREFIX + name)
	first_admission = frappe.cache.set(marker, 1, nx=True, ex=expires_at - now + 1)
	if calls == 0 and not first_admission:
		return "token_call_state_lost"
	if calls >= max_calls:
		return "token_call_limit"
	frappe.db.set_value(MCP_BUDGET, name, "calls", calls + 1, update_modified=False)

	# A row becomes eligible only well after its token has expired.
	expired = frappe.qb.get_query(
		MCP_BUDGET,
		filters={"expires_at": ("<=", now - MCP_BUDGET_RETENTION_SECONDS)},
		fields=["name"],
		order_by="expires_at asc, name asc",
		limit=20,
		for_update=True,
		skip_locked=True,
	).run(pluck=True)
	if expired:
		frappe.db.delete(MCP_BUDGET, {"name": ("in", expired)})
	return None
