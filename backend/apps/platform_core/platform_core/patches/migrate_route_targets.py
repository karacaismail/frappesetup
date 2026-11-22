"""Preserve the order of route targets from the legacy JSON column."""

from uuid import uuid4

import frappe

from platform_core.model_gateway.doctype.validation import parse_records

TARGET_DOCTYPE = "PLT AI Route Target"


def execute():
	# Frappe retains removed database columns. New installations have no JSON column.
	if not frappe.db.has_column("PLT AI Route", "targets"):
		return

	route = frappe.qb.DocType("PLT AI Route")
	for row in frappe.qb.from_(route).select(route.name, route.targets).run(as_dict=True):
		migrate_route(row.name, row.targets)


def migrate_route(name, legacy_json):
	link = {"parent": name, "parenttype": "PLT AI Route", "parentfield": "targets"}
	targets = parse_records(legacy_json, "Targets")
	if not targets:
		return
	for entry in targets:
		if not isinstance(entry, dict) or set(entry) != {"model", "api"}:
			raise ValueError(f"Invalid legacy model/API pair in route {name}")
		if any(not isinstance(value, str) or not value or value != value.strip() for value in entry.values()):
			raise ValueError(f"Invalid legacy model/API reference in route {name}")

	existing = frappe.get_all(TARGET_DOCTYPE, filters=link, fields=["model", "api"], order_by="idx asc")
	if existing:
		if existing != targets:
			raise ValueError(f"Existing child targets conflict with legacy targets in route {name}")
		return

	for index, entry in enumerate(targets, start=1):
		# Preserve existing references without triggering parent save or policy checks.
		frappe.get_doc(
			{"doctype": TARGET_DOCTYPE, "name": uuid4().hex, **link, "idx": index, **entry}
		).db_insert()
