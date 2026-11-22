"""Ordered model and API selection within a route."""

from hashlib import sha256

import frappe
from frappe.model.document import Document


class PLTAIRouteTarget(Document):
	pass


def on_doctype_update():
	# Frappe's MariaDB constraint lookup does not filter by database.
	database_key = sha256(frappe.db.cur_db_name.encode()).hexdigest()[:32]
	frappe.db.add_unique(
		"PLT AI Route Target",
		["parent", "model", "api"],
		constraint_name=f"unique_route_target_{database_key}",
	)
