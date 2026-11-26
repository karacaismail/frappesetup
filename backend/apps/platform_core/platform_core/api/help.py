"""HTTP entry points for field help (G-138). The rules are in `platform_core.shell.help`.

Contract: `backend/contracts/platform_core-help.openapi.yaml`.
"""

import frappe
from frappe.rate_limiter import rate_limit

from platform_core.shell.help import get_field_help as read_field_help
from platform_core.shell.help import get_help_coverage as read_help_coverage
from platform_core.shell.http import require_session
from platform_core.shell.request_policy import BootstrapQuery, validate_query


class FieldHelpQuery(BootstrapQuery):
	doctype: str
	fieldname: str
	language: str | None = None


class HelpCoverageQuery(BootstrapQuery):
	app: str


# The shell metadata function checks the DocType permission and the field's permission level.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=240, seconds=60, user_based=True, ip_based=False, methods=["GET"])
def get_field_help(doctype: str = "", fieldname: str = "", language: str | None = None) -> dict:
	"""Read the help of one field the current user can read. Changes no record."""
	user = require_session()
	validate_query(FieldHelpQuery)
	return read_field_help(doctype, fieldname, user, language or None)


# `read_help_coverage` starts with `frappe.only_for("System Manager")`.
@frappe.whitelist(methods=["GET"])  # nosemgrep: frappe-missing-permission
def get_help_coverage(app: str = "") -> dict:
	"""Report the share of fields with help in one installed application. System Manager only."""
	require_session()
	validate_query(HelpCoverageQuery)
	return read_help_coverage(app)
