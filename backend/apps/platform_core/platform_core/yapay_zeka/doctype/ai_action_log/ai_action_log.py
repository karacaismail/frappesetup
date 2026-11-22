"""AI Action Log: the immutable log of AI calls (G-64)."""

import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.yapay_zeka.errors import CONTEXT


class AIActionLog(Document):
	def validate(self) -> None:
		if not self.is_new():
			frappe.throw(_("AI Action Log is append-only.", context=CONTEXT), frappe.PermissionError)

	def on_trash(self) -> None:
		# Only the `retention.purge` command deletes old records, once the retention period is over.
		if self.flags.retention_purge:
			return
		frappe.throw(_("AI Action Log entries cannot be deleted.", context=CONTEXT), frappe.PermissionError)
