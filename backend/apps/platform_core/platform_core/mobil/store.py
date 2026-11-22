"""Frappe storage for internal mobile metadata."""

import json
import time
from datetime import UTC, datetime, timedelta

import frappe

from .protocol import DELIVERY_AUDIT_SIZE, MobileError, content_digest

SEQUENCE_DOCTYPE = "Mobile Sequence"
SEQUENCE_NAME = "site"
DELIVERY_AUDIT_INTERVAL = timedelta(minutes=5)
INTERNAL_TYPES = frozenset(
	{
		SEQUENCE_DOCTYPE,
		"Mobile Account State",
		"Mobile Installation",
		"Mobile Revoked Session",
		"Mobile Operation",
		"Mobile Change",
		"Mobile Delivery",
	}
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


def _select(doctype, fields, filters, *, limit=None, order_by=None, for_update=False):
	return frappe.qb.get_query(
		doctype,
		fields=fields,
		filters=filters,
		limit=limit,
		order_by=order_by,
		for_update=for_update,
	).run(as_dict=True)


def _sequence_row(*, for_update=False):
	row = frappe.db.get_value(
		SEQUENCE_DOCTYPE,
		SEQUENCE_NAME,
		["sequence", "retention_floor"],
		as_dict=True,
		for_update=for_update,
	)
	if row is None:
		raise MobileError("mobile_schema_unavailable", 503)
	return row


class MobileStore:
	def __init__(self):
		row = _sequence_row()
		self.sequence = row.sequence
		self.retention_floor = row.retention_floor
		self.pending_events = False

	def install(self, identity, installation_id, *, check_new=None):
		sid = getattr(identity, "sid", None)
		# Registration and token refresh cannot move the clock past actual authentication.
		authenticated_at = (
			getattr(identity, "auth_time", None) if sid else getattr(identity, "issued_at", None)
		)
		current = self._installation(installation_id, for_update=True)
		if current is None:
			if check_new is not None:
				check_new(identity)
			_insert(
				"Mobile Installation",
				installation_id=installation_id,
				account=identity.account,
				scope=identity.scope,
				principal=identity.principal,
				session_id=sid,
				session_bound_at=str(authenticated_at or 0),
			)
		elif not self._matches(current, identity) or (current.session_id and not sid):
			raise MobileError("installation_unavailable", 403)
		elif sid and current.session_id != sid:
			from .sessions import revoke_after_commit

			frappe.db.set_value(
				"Mobile Installation",
				installation_id,
				{"session_id": sid, "session_bound_at": str(authenticated_at or 0)},
			)
			revoke_after_commit((current.session_id,))
		elif authenticated_at and authenticated_at > int(current.session_bound_at or 0):
			frappe.db.set_value(
				"Mobile Installation", installation_id, "session_bound_at", str(authenticated_at)
			)
		return {"installation_id": installation_id}

	def _installation(self, installation_id, *, for_update=False):
		return frappe.db.get_value(
			"Mobile Installation",
			installation_id,
			[
				"account",
				"scope",
				"principal",
				"revoked",
				"session_id",
				"last_user_activity_at",
				"session_bound_at",
				"creation",
			],
			as_dict=True,
			for_update=for_update,
		)

	def _matches(self, row, identity):
		return (
			row is not None
			and not row.revoked
			and row.account == identity.account
			and row.scope == identity.scope
			and row.principal == identity.principal
		)

	def require_installation(self, identity, installation_id, *, for_update=False):
		row = self._installation(installation_id, for_update=for_update)
		if not self._matches(row, identity) or (row.session_id or None) != getattr(identity, "sid", None):
			raise MobileError("installation_unavailable", 403)

		return row

	def list_owned_installations(self, identity, after):
		filters = {"account": identity.account, "principal": identity.principal}
		if after is not None:
			filters["name"] = [">", after]
		rows = _select(
			"Mobile Installation", ["name", "scope", "revoked"], filters, limit=21, order_by="name asc"
		)
		return {
			"installations": [
				{"installation_id": row.name, "scope": row.scope, "revoked": bool(row.revoked)}
				for row in rows[:20]
			],
			"next_after": rows[19].name if len(rows) > 20 else None,
		}

	def revoke_owned_installation(self, identity, installation):
		row = self._installation(installation, for_update=True)
		if row is None or row.account != identity.account or row.principal != identity.principal:
			raise MobileError("installation_unavailable", 404)
		return {"revoked": self.revoke_targets((installation,))}

	def revoke(self, identity, installation_id):
		rows = self.revocation_targets(
			identity.account,
			installation_id,
			scope=identity.scope,
			principal=identity.principal,
			include_revoked=installation_id is not None,
		)
		return {"revoked": self.revoke_targets(row.name for row in rows)}

	def revoke_account_installations(self, account):
		rows = self.revocation_targets(account, include_revoked=True)
		changed = self.revoke_targets((row.name for row in rows), remote=False)

		# Update only rows with a binding so a repeated call does not change them.
		frappe.db.set_value(
			"Mobile Installation",
			{"account": account, "notification_token": ["is", "set"]},
			"notification_token",
			None,
		)
		return len(rows), changed

	def revocation_targets(
		self, account, installation_id=None, *, scope=None, principal=None, include_revoked=False
	):
		filters = {"account": account}
		if not include_revoked:
			filters["revoked"] = 0
		if scope is not None:
			filters["scope"] = scope
		if principal is not None:
			filters["principal"] = principal
		if installation_id is not None:
			filters["name"] = installation_id
		return _select(
			"Mobile Installation",
			["name", "revoked", "session_id"],
			filters,
			order_by="name asc",
			for_update=True,
		)

	def revoke_targets(self, installation_ids, *, remote=True):
		from .sessions import revoke_after_commit

		count = 0
		session_ids = set()
		for installation_id in installation_ids:
			row = frappe.db.get_value(
				"Mobile Installation",
				installation_id,
				["revoked", "session_id", "notification_token"],
				as_dict=True,
				for_update=True,
			)
			if row is None:
				continue
			if row.session_id:
				session_ids.add(row.session_id)
			if not row.revoked or row.notification_token is not None:
				frappe.db.set_value(
					"Mobile Installation", installation_id, {"revoked": 1, "notification_token": None}
				)
				count += int(not row.revoked)
		revoke_after_commit(session_ids, remote=remote)
		return count

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
		# Keep allocation and insertion under the same transaction lock.
		current = _sequence_row(for_update=True).sequence
		if current == 2_147_483_647:
			raise MobileError("mobile_sequence_exhausted", 503)
		sequence = current + 1
		_insert(
			"Mobile Change",
			sequence=sequence,
			record_type=record_type,
			record_id=record_id,
			kind=kind,
			target_installation=target_installation,
		)
		frappe.db.set_value(SEQUENCE_DOCTYPE, SEQUENCE_NAME, "sequence", sequence)
		# A locking read can see commits outside the caller's read snapshot.
		# Keep the cursor below any events the snapshot cannot yet read.
		if current == self.sequence:
			self.sequence = sequence
		else:
			self.pending_events = True
		return sequence

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
			for_update=True,
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
		return frappe.db.get_value("Mobile Delivery", key, "name") is not None

	def record_delivery(self, installation, record_type, record_id):
		key = content_digest([installation, record_type, record_id])
		row = frappe.db.get_value("Mobile Delivery", key, ["name", "visible"], as_dict=True, for_update=True)
		if row is not None:
			if not row.visible:
				frappe.db.set_value("Mobile Delivery", row.name, "visible", 1)
			return
		_insert(
			"Mobile Delivery",
			delivery_key=key,
			installation_id=installation,
			record_type=record_type,
			record_id=record_id,
		)

	def audit_due(self, installation, now):
		last_audit = frappe.db.get_value("Mobile Installation", installation, "last_audit_at")
		at = datetime.fromtimestamp(now, UTC).replace(tzinfo=None)
		return last_audit is None or at - last_audit >= DELIVERY_AUDIT_INTERVAL

	def finish_audit(self, installation, now):
		at = datetime.fromtimestamp(now, UTC).replace(tzinfo=None)
		frappe.db.set_value("Mobile Installation", installation, "last_audit_at", at)


def delete_user_state(user, method=None):
	"""Remove installation metadata before Frappe checks links to the user."""
	frappe.db.delete("Mobile Account State", {"account": user.name})
	rows = _select("Mobile Installation", ["name"], {"account": user.name}, for_update=True)
	if rows:
		installations = ["in", [row.name for row in rows]]
		frappe.db.delete("Mobile Change", {"target_installation": installations})
		frappe.db.delete("Mobile Delivery", {"installation_id": installations})
		frappe.db.delete("Mobile Installation", {"name": installations})


def cleanup(dry_run=False):
	"""Preserve the original operator command path."""
	from .retention import cleanup as cleanup_retention

	return cleanup_retention(dry_run=dry_run)
