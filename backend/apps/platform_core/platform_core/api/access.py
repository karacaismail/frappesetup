"""Erişim kuralı uçları. İş kuralı `platform_core.erisim` modülündedir.

Sözleşme: `backend/contracts/platform_core-erisim.openapi.yaml`.
"""

import frappe
from frappe import _

from platform_core.erisim import explain, field_level


@frappe.whitelist(methods=["GET"])
def explain_permission(doctype: str, name: str, ptype: str = "read", user: str | None = None) -> dict:
	"""Bir kayıtta iznin nedenini açıklar. Kayıt değiştirmez."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No permission to read {0}.").format(doctype), frappe.PermissionError)
	return explain.explain(doctype, name, ptype, user)


@frappe.whitelist(methods=["GET"])
def get_access_summary(doctype: str) -> dict:
	"""Oturum sahibinin bir kayıt türündeki kural kapsamlarını döner."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No permission to read {0}.").format(doctype), frappe.PermissionError)
	return explain.summary(doctype)


@frappe.whitelist(methods=["POST"])
def set_field_level(doctype: str, fieldname: str, permlevel: int) -> dict:
	"""Bir alanın izin seviyesini değiştirir. Yalnız “System Manager”."""
	if not frappe.has_permission("Property Setter", "create"):
		frappe.throw(_("No permission to change field levels."), frappe.PermissionError)
	return field_level.set_field_level(doctype, fieldname, permlevel)


@frappe.whitelist(methods=["POST"])
def set_level_access(doctype: str, role: str, permlevel: int, read: bool, write: bool) -> dict:
	"""Bir role bir izin seviyesinde okuma ve yazma izni verir. Yalnız “System Manager”."""
	if not frappe.has_permission("Custom DocPerm", "write"):
		frappe.throw(_("No permission to change role permissions."), frappe.PermissionError)
	return field_level.set_level_access(doctype, role, permlevel, read, write)
