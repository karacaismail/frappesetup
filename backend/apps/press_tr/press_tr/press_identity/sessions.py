import frappe
from frappe.utils import password

SESSION_MAPPING_DOCTYPE = "PTR Keycloak Session"
SESSION_MAPPING_PAGE_SIZE = 100


def session_mapping_pages(filters: dict):
	while names := frappe.get_all(
		SESSION_MAPPING_DOCTYPE,
		filters=filters,
		pluck="name",
		order_by="name asc",
		limit=SESSION_MAPPING_PAGE_SIZE,
	):
		yield names
		if len(names) < SESSION_MAPPING_PAGE_SIZE:
			return
		filters = {**filters, "name": [">", names[-1]]}


def read_press_session_id(mapping: str) -> str:
	return password.get_decrypted_password(SESSION_MAPPING_DOCTYPE, mapping, "press_sid")


def remove_mapping(login_manager=None):
	user, sid = frappe.session.user, frappe.session.sid
	if user == "Guest":
		return
	link = frappe.db.get_value("PTR Identity Link", {"user": user}, "name")
	if not link:
		return
	for names in session_mapping_pages({"identity_link": link}):
		for name in names:
			if read_press_session_id(name) == sid:
				# Frappe has authorized logout of this exact session.
				frappe.delete_doc(SESSION_MAPPING_DOCTYPE, name, ignore_permissions=True)
