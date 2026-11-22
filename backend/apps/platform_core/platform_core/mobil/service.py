"""Process authorized mobile commands and assemble bounded sync pages."""

from itertools import islice

from .protocol import (
	BATCH_SIZE,
	PAGE_SIZE,
	MobileError,
	check_version,
	content_digest,
	decode_cursor,
	encode_cursor,
	operation_key,
	unavailable_record,
	validate_operation,
)

# A record type may be registered after its offline plan and permissions are reviewed.
COMMANDS = {}


def push(store, commands, site, account, operations, *, principal, disabled_commands=()):
	"""Apply the batch atomically. The caller owns commit and rollback."""
	if not isinstance(operations, list) or not 1 <= len(operations) <= BATCH_SIZE:
		raise MobileError("invalid_batch_size")

	declarations = {name: handler.declaration for name, handler in commands.items()}
	pending = []
	for operation in operations:
		if not isinstance(operation, dict):
			raise MobileError("invalid_operation")
		key = operation_key(site, principal, operation.get("operation_id"))
		digest = content_digest(operation)
		pending.append((operation, key, digest))

	results = []
	for operation, key, digest in pending:
		saved = store.get_operation(key)
		if saved is not None:
			previous_digest, result = saved
			if previous_digest != digest:
				raise MobileError("operation_conflict", 409)
			results.append(result)
			continue

		command = validate_operation(operation, declarations)
		name = operation["command"]
		if name in disabled_commands:
			raise MobileError("command_disabled", 403)
		handler = commands[name]
		record_id = operation["record_id"]
		handler.authorize(account, record_id)
		if command.action != "create":
			current = handler.read_locked(account, record_id)
			if current is None:
				raise unavailable_record()
			check_version(operation["version"], current)

		handler.apply(account, record_id, operation.get("fields", {}))
		kind = "remove" if command.action == "delete" else "upsert"
		store.append_change(handler.record_type, record_id, kind)

		# Replays disclose only acceptance of this same account's submitted operation.
		result = {"operation_id": operation["operation_id"], "status": "applied"}
		store.remember_operation(key, digest, result)
		results.append(result)

	return {"operations": results}


def _snapshot_candidates(inventories, account, position, limit):
	"""Each scanner reads at most the requested IDs in ascending UUID order."""
	previous_type, previous_id = position or ("", None)
	candidates = []
	for record_type, scan in sorted(inventories.items()):
		if record_type < previous_type:
			continue
		after = previous_id if record_type == previous_type else None
		remaining = limit - len(candidates)
		candidates.extend(
			(record_type, record_id) for record_id in islice(scan(account, after, remaining), remaining)
		)
		if len(candidates) >= limit:
			break
	return candidates


def _pull_changes(store, projections, installation, account, candidates, *, snapshot):
	changes = []
	for record_type, record_id in candidates:
		identity = {"record_type": record_type, "record_id": record_id}
		projection = projections.get(record_type)
		current = projection(account, record_id) if projection else None
		if current is not None:
			store.record_delivery(installation, record_type, record_id)
			changes.append(
				{"kind": "upsert", **identity, "version": current["version"], "fields": current["fields"]}
			)
		elif not snapshot and store.may_have_delivered(installation, record_type, record_id):
			changes.append({"kind": "remove", **identity})
	return changes


def pull(store, projections, secret, scope, cursor, limit, *, account, now, inventories=None):
	"""Read the current inventory first, then consume committed change events."""
	if type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
		raise MobileError("invalid_page_size")

	_unused, _unused, installation, _unused = scope
	if cursor is None:
		after, ceiling, snapshot, delivery_after, snapshot_after = 0, store.sequence, True, None, None
	else:
		after, ceiling, snapshot, delivery_after, snapshot_after = decode_cursor(
			secret,
			scope,
			cursor,
			now=now,
			floor=store.retention_floor,
		)

	if snapshot:
		candidates = _snapshot_candidates(inventories or {}, account, snapshot_after, limit + 1)
		has_more = len(candidates) > limit
		snapshot_after = candidates[limit - 1] if has_more else None
		position = after if has_more else ceiling
	else:
		if delivery_after is not None or (after == ceiling and store.audit_due(installation, now)):
			delivery_after = store.reconcile_deliveries(projections, installation, account, delivery_after)
			if delivery_after is None:
				store.finish_audit(installation, now)
		if after == ceiling:
			ceiling = store.sequence
		events = store.read_events(installation, after, ceiling, limit + 1)
		candidates = [(event.record_type, event.record_id) for event in events]
		more_events = len(events) > limit
		position = events[limit - 1].sequence if more_events else ceiling
		has_more = (
			more_events or delivery_after is not None or position < store.sequence or store.pending_events
		)

	return {
		"changes": _pull_changes(
			store, projections, installation, account, candidates[:limit], snapshot=snapshot
		),
		"cursor": encode_cursor(
			secret,
			scope,
			after=position,
			ceiling=ceiling,
			now=now,
			snapshot=snapshot and has_more,
			delivery_after=delivery_after,
			snapshot_after=snapshot_after,
		),
		"has_more": has_more,
	}
