"""Give proposals opened before AJA-1001 a risk level from their stored tool flags.

An app tool's own declared level was not stored then, so the computed level is used.
"""

from platform_core.ai import risk, store


def execute():
	for row in store.proposals_without_risk_level():
		level = risk.computed(
			kind="write",
			tool_class=row.tool_class or "",
			destructive=bool(row.destructive),
			billable=bool(row.billable),
		)
		store.backfill_risk_level(row.name, level)
