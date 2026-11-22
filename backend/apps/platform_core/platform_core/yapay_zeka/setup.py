"""Kurulum ve migrate adımları."""

import frappe


def disable_builtin_mcp() -> None:
	"""Frappe'nin hazır MCP ucunu kapatır.

	Hazır uç (`/api/v2/mcp`) önizleme, onay ve işlem günlüğü taşımaz. Açık kalırsa
	yapay zekâ onaysız yazabilir. Karar: docs/kararlar/0002-yapay-zeka-katmani.md.

	`set_single_value` bilinçli seçildi: kurulum adımı tek bir ayarı kapatır ve
	System Settings doğrulamalarının kurulum sırasında çalışması gerekmez.
	"""
	if frappe.db.get_single_value("System Settings", "enable_mcp"):
		frappe.db.set_single_value("System Settings", "enable_mcp", 0)
