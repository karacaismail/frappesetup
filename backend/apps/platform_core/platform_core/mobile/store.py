"""Frappe storage for internal mobile metadata."""

import json
from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from .protocol import DELIVERY_AUDIT_SIZE, RETENTION_DAYS, MobileError, content_digest

SEQUENCE_DOCTYPE = "Mobile Sequence"
SEQUENCE_NAME = "site"
INTERNAL_TYPES = frozenset(
	{SEQUENCE_DOCTYPE, "Mobile Installation", "Mobile Operation", "Mobile Change", "Mobile Delivery"}
)


def seed_sequence():
	"""Create the lock row after Frappe has synchronized the schema."""
	if not frappe.db.exists(SEQUENCE_DOCTYPE, SEQUENCE_NAME):
		_insert(SEQUENCE_DOCTYPE, sequence_key=SEQUENCE_NAME, ignore_duplicate=True)


def _insert(doctype, *, ignore_duplicate=False, **fields):
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


def _select(doctype, fields, filters, *, limit=None, order_by=None):
	return frappe.qb.get_query(
		doctype,
		fields=fields,
		filters=filters,
		limit=limit,
		order_by=order_by,
		for_update=True,
	).run(as_dict=True)


class MobileStore:
	def __init__(self):
		# Obtain the site lock before reading device, delivery or operation state.
		# No request may commit before its event and operation result are durable.
		row = frappe.db.get_value(
			SEQUENCE_DOCTYPE,
			SEQUENCE_NAME,
			["sequence", "retention_floor"],
			as_dict=True,
			for_update=True,
		)
		if row is None:
			raise MobileError("mobile_schema_unavailable", 503)
		self.sequence = row.sequence
		self.retention_floor = row.retention_floor

	def install(self, identity, installation_id):
		current = self._installation(installation_id)
		if current is None:
			_insert(
				"Mobile Installation",
				installation_id=installation_id,
				account=identity.account,
				scope=identity.scope,
				principal=identity.principal,
			)
		elif not self._matches(current, identity):
			raise MobileError("installation_unavailable", 403)
		return {"installation_id": installation_id}

	def _installation(self, installation_id):
		return frappe.db.get_value(
			"Mobile Installation",
			installation_id,
			["account", "scope", "principal", "revoked"],
			as_dict=True,
			for_update=True,
		)

	def _matches(self, row, identity):
		return (
			row is not None
			and not row.revoked
			and row.account == identity.account
			and row.scope == identity.scope
			and row.principal == identity.principal
		)

	def require_installation(self, identity, installation_id):
		if not self._matches(self._installation(installation_id), identity):
			raise MobileError("installation_unavailable", 403)

	def revoke(self, identity, installation_id):
		filters = {
			"account": identity.account,
			"scope": identity.scope,
			"principal": identity.principal,
			"revoked": 0,
		}
		if installation_id is not None:
			filters["name"] = installation_id
		rows = _select("Mobile Installation", ["name"], filters)
		for row in rows:
			frappe.db.set_value("Mobile Installation", row.name, "revoked", 1)
		return {"revoked": len(rows)}

	def get_operation(self, key):
		row = frappe.db.get_value(
			"Mobile Operation",
			key,
			["content_digest", "result"],
			as_dict=True,
			for_update=True,
		)
		if row:
			result = json.loads(row.result) if isinstance(row.result, str) else row.result
			return row.content_digest, result
		return None

	def remember_operation(self, key, digest, result):
		_insert("Mobile Operation", operation_key=key, content_digest=digest, result=result)

	def append_change(self, record_type, record_id, kind, *, target_installation=None):
		if self.sequence == 2_147_483_647:
			raise MobileError("mobile_sequence_exhausted", 503)
		self.sequence += 1
		_insert(
			"Mobile Change",
			sequence=self.sequence,
			record_type=record_type,
			record_id=record_id,
			kind=kind,
			target_installation=target_installation,
		)
		frappe.db.set_value(SEQUENCE_DOCTYPE, SEQUENCE_NAME, "sequence", self.sequence)

	def read_events(self, installation, after, ceiling, limit):
		event = frappe.qb.DocType("Mobile Change")
		return (
			frappe.qb.from_(event)
			.select(event.sequence, event.record_type, event.record_id)
			.where((event.sequence > after) & (event.sequence <= ceiling))
			.where(
				event.target_installation.isnull()
				| (event.target_installation == "")
				| (event.target_installation == installation)
			)
			.orderby(event.sequence)
			.limit(limit)
			.for_update()
			.run(as_dict=True)
		)

	def reconcile_deliveries(self, projections, installation, account, after):
		filters = {"installation_id": installation}
		if after:
			filters["name"] = [">", after]
		rows = _select(
			"Mobile Delivery",
			["name", "record_type", "record_id", "visible"],
			filters,
			limit=DELIVERY_AUDIT_SIZE + 1,
			order_by="name asc",
		)
		for row in rows[:DELIVERY_AUDIT_SIZE]:
			projection = projections.get(row.record_type)
			visible = projection is not None and projection(account, row.record_id) is not None
			if visible != bool(row.visible):
				kind = "upsert" if visible else "remove"
				self.append_change(row.record_type, row.record_id, kind, target_installation=installation)
				frappe.db.set_value("Mobile Delivery", row.name, "visible", int(visible))

		if len(rows) > DELIVERY_AUDIT_SIZE:
			return rows[DELIVERY_AUDIT_SIZE - 1].name
		return None

	def may_have_delivered(self, installation, record_type, record_id):
		key = content_digest([installation, record_type, record_id])
		return frappe.db.get_value("Mobile Delivery", key, "name", for_update=True) is not None

	def record_delivery(self, installation, record_type, record_id):
		if self.may_have_delivered(installation, record_type, record_id):
			return
		key = content_digest([installation, record_type, record_id])
		_insert(
			"Mobile Delivery",
			delivery_key=key,
			installation_id=installation,
			record_type=record_type,
			record_id=record_id,
		)

	def cleanup(self):
		cutoff = now_datetime() - timedelta(days=RETENTION_DAYS)
		filters = {"kind": "remove", "creation": ["<", cutoff]}
		# Bound the transaction. Staff may invoke the command again to finish.
		rows = _select("Mobile Change", ["name", "sequence"], filters, limit=1000)
		if rows:
			names = [row.name for row in rows]
			new_floor = max(self.retention_floor, *(row.sequence for row in rows))
			frappe.db.delete("Mobile Change", {"name": ["in", names]})
			frappe.db.set_value(SEQUENCE_DOCTYPE, SEQUENCE_NAME, "retention_floor", new_floor)
		return {"removed": len(rows)}


def cleanup():
	"""Manual bench command; HTTP performs its separate site-role check first."""
	return MobileStore().cleanup()
