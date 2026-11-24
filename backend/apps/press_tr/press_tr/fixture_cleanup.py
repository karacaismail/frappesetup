"""G-8: close Frappe Cloud defaults after Press imports its fixtures.

Frappe runs ``sync_fixtures`` before ``after_migrate``. A Press fixture with a newer ``modified``
stamp overwrites local edits, so every step here runs again on every migrate. Writes use
``update_modified=False`` so Press document events do not run and the import stamp stays.

Two values are human decisions and come from site config, never from this file:

- ``press_tr_team_tiers``: the approved Team Tier table (product owner, G-166 price gate).
- ``press_tr_enabled_clusters``: the Cluster names in use (infrastructure owner).

When a value is missing, its step changes nothing.
"""

import json
from pathlib import Path

import frappe

LEGACY_SIGNUP_METHOD = "press.signup_e2e.run_signup_e2e"
TEAM_TIERS_KEY = "press_tr_team_tiers"
ENABLED_CLUSTERS_KEY = "press_tr_enabled_clusters"
TEAM_TIER_FIELDS = ("amount", "last_invoice_amount")
TEAM_TIER_OPTIONAL_FIELDS = ("paying_user_since",)


def disable_cloud_defaults():
	disable_press_site_plans()
	stop_legacy_signup_job()
	apply_team_tiers()
	close_unused_clusters()


def disable_press_site_plans():
	fixture = Path(frappe.get_app_path("press", "fixtures", "site_plan.json"))
	plans = [row["name"] for row in json.loads(fixture.read_text(encoding="utf-8"))]
	# Plans that are not in the Press fixture are ours (G-9) and stay enabled.
	if plans:
		frappe.db.set_value(
			"Site Plan",
			{"name": ["in", plans], "enabled": 1},
			"enabled",
			0,
			update_modified=False,
		)


def stop_legacy_signup_job():
	# The OTP signup flow does not run under Keycloak sign-in.
	jobs = frappe.get_all(
		"Scheduled Job Type",
		filters=[["Scheduled Job Type", "method", "=", LEGACY_SIGNUP_METHOD]],
		pluck="name",
	)
	if jobs:
		frappe.db.set_value(
			"Scheduled Job Type",
			{"name": ["in", jobs], "stopped": 0},
			"stopped",
			1,
			update_modified=False,
		)


def apply_team_tiers():
	table = frappe.conf.get(TEAM_TIERS_KEY)
	if not table:
		return
	tiers = frappe.get_all("Team Tier", pluck="name")
	rows = _validated_team_tiers(table, tiers)
	for tier, values in rows.items():
		frappe.db.set_value("Team Tier", tier, values, update_modified=False)


def _validated_team_tiers(table, tiers):
	"""Check the whole table first, so a bad table changes no tier."""
	if not isinstance(table, dict) or set(table) != set(tiers):
		frappe.throw(frappe._("The Team Tier table must list every Press Team Tier exactly once."))
	rows = {}
	for tier, values in table.items():
		if not isinstance(values, dict) or not set(TEAM_TIER_FIELDS) <= set(values):
			frappe.throw(frappe._("Every Team Tier row needs amount and last_invoice_amount."))
		allowed = set(TEAM_TIER_FIELDS) | set(TEAM_TIER_OPTIONAL_FIELDS)
		if set(values) - allowed:
			frappe.throw(frappe._("The Team Tier table has an unknown field."))
		for field, value in values.items():
			if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
				frappe.throw(frappe._("Team Tier values must be numbers that are zero or more."))
		rows[tier] = dict(values)
	return rows


def close_unused_clusters():
	"""Hide unused Clusters and disable their Server Plans.

	Cloud Region has no enabled field, so the region record is kept as it is. A Server Plan
	without a Cluster is not tied to a region and stays unchanged.
	"""
	enabled = frappe.conf.get(ENABLED_CLUSTERS_KEY)
	if not enabled:
		return
	if not isinstance(enabled, list) or not all(isinstance(name, str) and name for name in enabled):
		frappe.throw(frappe._("The enabled Cluster list must be a list of Cluster names."))

	clusters = frappe.get_all("Cluster", filters=[["Cluster", "name", "not in", enabled]], pluck="name")
	if clusters:
		frappe.db.set_value(
			"Cluster", {"name": ["in", clusters], "public": 1}, "public", 0, update_modified=False
		)

	plans = frappe.get_all(
		"Server Plan",
		filters=[
			["Server Plan", "cluster", "is", "set"],
			["Server Plan", "cluster", "not in", enabled],
		],
		pluck="name",
	)
	if plans:
		frappe.db.set_value(
			"Server Plan", {"name": ["in", plans], "enabled": 1}, "enabled", 0, update_modified=False
		)
