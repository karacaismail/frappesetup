"""Install and migrate steps."""

import frappe


def disable_builtin_mcp() -> None:
	"""Turn off Frappe's built-in MCP endpoint.

	The built-in endpoint (`/api/v2/mcp`) has no preview, approval or action log. If it stays
	on, AI can write without approval. Decision: docs/kararlar/0002-yapay-zeka-katmani.md.

	`set_single_value` is a deliberate choice: the install step turns off a single setting and
	the System Settings validations do not need to run during install.
	"""
	if frappe.db.get_single_value("System Settings", "enable_mcp"):
		frappe.db.set_single_value("System Settings", "enable_mcp", 0)
