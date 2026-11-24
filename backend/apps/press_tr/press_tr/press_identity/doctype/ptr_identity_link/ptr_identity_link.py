import frappe
from frappe.model.document import Document


class PTRIdentityLink(Document):
	pass


def on_doctype_update():
	frappe.db.add_unique("PTR Identity Link", ["issuer", "subject"])
