import frappe
from frappe.sessions import get_expired_threshold
from frappe.utils import get_datetime


@frappe.whitelist(methods=["POST"])
def cleanup_expired_sessions() -> dict[str, int]:
	frappe.only_for("System Manager")
	threshold = get_datetime(get_expired_threshold())
	removed = 0
	for name in frappe.get_all("Press Keycloak Session", pluck="name"):
		try:
			record = frappe.get_doc("Press Keycloak Session", name, for_update=True)
		except frappe.DoesNotExistError:
			continue
		sid = record.get_password("press_sid")
		last_update = frappe.db.get_value(
			"Sessions", {"sid": sid}, "lastupdate", for_update=True, order_by=None
		)
		if not last_update or get_datetime(last_update) < threshold:
			# System Manager maintenance can remove expired internal mappings.
			record.delete(ignore_permissions=True)
			removed += 1
	return {"removed": removed}
