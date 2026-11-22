"""Ordered model and API selection within a route."""

from hashlib import sha256

import frappe
from frappe.model.document import Document

TARGET_DOCTYPE = "PLT AI Route Target"
TARGET_FIELDS = ("parent", "model", "api")


class PLTAIRouteTarget(Document):
	pass


def _has_equivalent_mariadb_index():
	indexes = {}
	for row in frappe.db.sql(
		"""select INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART
		   from information_schema.STATISTICS
		   where TABLE_SCHEMA = database() and TABLE_NAME = %s and NON_UNIQUE = 0""",
		(f"tab{TARGET_DOCTYPE}",),
	):
		name, position, column, prefix = row
		indexes.setdefault(name, {})[position] = column if prefix is None else None
	return any(
		tuple(fields[position] for position in sorted(fields)) == TARGET_FIELDS for fields in indexes.values()
	)


def on_doctype_update():
	# A restore can retain the same complete index under the old database's name.
	if frappe.db.db_type == "mariadb" and _has_equivalent_mariadb_index():
		return

	# Frappe's MariaDB constraint lookup does not filter by database.
	database_key = sha256(frappe.db.cur_db_name.encode()).hexdigest()[:32]
	frappe.db.add_unique(
		TARGET_DOCTYPE,
		list(TARGET_FIELDS),
		constraint_name=f"unique_route_target_{database_key}",
	)
