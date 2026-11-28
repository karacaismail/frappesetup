"""Export the current corporate provider exceptions for the apply command (G-160, AJA-229).

Frappe never writes Keycloak. The DevOps owner runs two steps by hand:

1. `bench --site <site> execute platform_core.identity.enterprise_sync.export_exceptions
   --kwargs '{"path": "<file>"}'` writes the current grants to a JSON file.
2. `bin/atonota-login apply --from-env --enterprise-exceptions <file>` checks every corporate
   provider against the file.

The file holds only the record fields and no secret. It is written with mode 0600 and must not be
committed to Git. The file is not signed: the apply command checks the rules again, but it cannot
prove from the file alone that the approval was given. Only the DevOps owner carries the file.

No scheduled job runs this export.
"""

from __future__ import annotations

import json
import os

import frappe

from platform_core.identity import enterprise_membership, enterprise_rules


def current_grants() -> list[dict]:
	"""Every current grant, checked by the rules. A rule break stops the export."""
	# list-limit: the export must hold every provider and organisation pair. A manager adds each pair.
	pairs = frappe.get_all(
		enterprise_membership.DOCTYPE,
		fields=["provider_alias", "organization"],
		distinct=True,
		order_by="provider_alias asc, organization asc",
	)
	records = []
	for pair in pairs:
		doc = enterprise_membership.current_exception(pair.provider_alias, pair.organization)
		if doc is None:
			continue
		record = enterprise_membership.to_record(doc)
		enterprise_membership.check_or_throw(enterprise_rules.check_record, record)
		records.append(record)
	return records


def export_exceptions(path: str) -> int:
	"""Write the current grants to `path` with mode 0600. Returns the number of records."""
	frappe.only_for(enterprise_membership.APPROVER_ROLE)
	records = current_grants()
	descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
		os.fchmod(handle.fileno(), 0o600)
		json.dump(records, handle, indent=2, sort_keys=True)
		handle.write("\n")
	return len(records)
