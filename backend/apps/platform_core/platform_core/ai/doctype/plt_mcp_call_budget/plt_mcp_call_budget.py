"""Internal counter. Only the OAuth tool admission path writes it."""

import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.ai.errors import CONTEXT


class PLTMCPCallBudget(Document):
	def validate(self) -> None:
		self._reject()

	def on_trash(self) -> None:
		self._reject()

	@staticmethod
	def _reject() -> None:
		frappe.throw(_("MCP call counters are internal.", context=CONTEXT), frappe.PermissionError)
