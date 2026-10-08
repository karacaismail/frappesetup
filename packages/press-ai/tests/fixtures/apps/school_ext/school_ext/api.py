import frappe


@frappe.whitelist(allow_guest=True)
def public_lookup(name):
	doc = frappe.get_doc({'doctype': 'Guardian Note', 'title': name})
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def report(student):
	return frappe.db.sql(f"select name from `tabStudent Record` where student = '{student}'")


def internal(doc):
	doc.insert(ignore_permissions=True)
