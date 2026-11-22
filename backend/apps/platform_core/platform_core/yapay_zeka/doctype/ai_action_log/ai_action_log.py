"""AI Action Log: yapay zekâ çağrılarının değişmeyen günlüğü (G-64)."""

import frappe
from frappe import _
from frappe.model.document import Document


class AIActionLog(Document):
	def validate(self) -> None:
		if not self.is_new():
			frappe.throw(_("AI Action Log is append-only."), frappe.PermissionError)

	def on_trash(self) -> None:
		# BORC(mvp): 365 günlük saklama süresi için elle başlatılan silme komutu yok.
		# Etki: günlük büyür. Sorumlu: platform-core-yz. Kapanma: komut ve HTTP ucu yazılır.
		frappe.throw(_("AI Action Log entries cannot be deleted."), frappe.PermissionError)
