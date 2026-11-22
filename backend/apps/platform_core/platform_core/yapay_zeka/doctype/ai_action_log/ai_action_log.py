"""AI Action Log: yapay zekâ çağrılarının değişmeyen günlüğü (G-64)."""

import frappe
from frappe import _
from frappe.model.document import Document


class AIActionLog(Document):
	def validate(self) -> None:
		if not self.is_new():
			frappe.throw(_("AI Action Log is append-only."), frappe.PermissionError)

	def on_trash(self) -> None:
		# Eski kayıtları yalnız `retention.purge` komutu, saklama süresi dolunca siler.
		frappe.throw(_("AI Action Log entries cannot be deleted."), frappe.PermissionError)
