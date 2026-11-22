import frappe
from frappe.model.document import Document


class PressIdentityLink(Document):
	pass


def on_doctype_update():
	frappe.db.add_unique("Press Identity Link", ["issuer", "subject"])
