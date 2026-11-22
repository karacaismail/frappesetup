import frappe


def remove_mapping(login_manager=None):
	user, sid = frappe.session.user, frappe.session.sid
	if user == "Guest":
		return
	link = frappe.db.get_value("Press Identity Link", {"user": user}, "name")
	if not link:
		return
	for name in frappe.get_all("Press Keycloak Session", filters={"identity_link": link}, pluck="name"):
		record = frappe.get_doc("Press Keycloak Session", name)
		if record.get_password("press_sid") == sid:
			# Frappe has authorized logout of this exact session.
			record.delete(ignore_permissions=True)
