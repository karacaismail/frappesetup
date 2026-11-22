"""Business commands run inside the caller's locked site transaction."""

from .protocol import (
	BATCH_SIZE,
	PAGE_SIZE,
	MobileError,
	check_version,
	content_digest,
	decode_cursor,
	encode_cursor,
	operation_key,
	validate_operation,
)

# A record type may be registered after its offline plan and permissions are reviewed.
COMMANDS = {}


def push(store, commands, site, account, operations, *, principal):
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
		handler = commands[operation["command"]]
		record_id = operation["record_id"]
		handler.authorize(account, record_id)
		if command.action != "create":
			current = handler.read_locked(account, record_id)
			if current is None:
				raise MobileError("record_not_found", 404)
			check_version(operation["version"], current)

		handler.apply(account, record_id, operation.get("fields", {}))
		kind = "remove" if command.action == "delete" else "upsert"
		store.append_change(handler.record_type, record_id, kind)

		# Replays disclose only acceptance of this same account's submitted operation.
		result = {"operation_id": operation["operation_id"], "status": "applied"}
		store.remember_operation(key, digest, result)
		results.append(result)

	return {"operations": results}


def pull(store, projections, secret, scope, cursor, limit, *, account, now):
	"""Read a bounded page using only committed sequence positions."""
	if type(limit) is not int or not 1 <= limit <= PAGE_SIZE:
		raise MobileError("invalid_page_size")

	_, _, installation, _ = scope
	if cursor is None:
		after, ceiling, snapshot, delivery_after = 0, store.sequence, True, None
	else:
		after, ceiling, snapshot, delivery_after = decode_cursor(
			secret,
			scope,
			cursor,
			now=now,
			floor=store.retention_floor,
		)

	if not snapshot and (after == ceiling or delivery_after is not None):
		delivery_after = store.reconcile_deliveries(projections, installation, account, delivery_after)
		ceiling = store.sequence

	events = store.read_events(installation, after, ceiling, limit + 1)
	more_events = len(events) > limit
	changes = []
	for event in events[:limit]:
		identity = {"record_type": event.record_type, "record_id": event.record_id}
		projection = projections.get(event.record_type)
		current = projection(account, event.record_id) if projection else None
		if current is not None:
			store.record_delivery(installation, event.record_type, event.record_id)
			changes.append(
				{"kind": "upsert", **identity, "version": current["version"], "fields": current["fields"]}
			)
		elif store.may_have_delivered(installation, event.record_type, event.record_id):
			changes.append({"kind": "remove", **identity})

	position = events[limit - 1].sequence if more_events else ceiling
	return {
		"changes": changes,
		"cursor": encode_cursor(
			secret,
			scope,
			after=position,
			ceiling=ceiling,
			now=now,
			snapshot=snapshot and more_events,
			delivery_after=delivery_after,
		),
		"has_more": more_events or delivery_after is not None,
	}
