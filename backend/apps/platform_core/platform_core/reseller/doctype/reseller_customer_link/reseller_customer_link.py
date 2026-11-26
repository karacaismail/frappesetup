"""The “Reseller Customer Link” record: one reseller tenant sees one customer tenant."""

from frappe.model.document import Document


class ResellerCustomerLink(Document):
	def validate(self):
		self.reseller_tenant = (self.reseller_tenant or "").strip()
		self.customer_tenant = (self.customer_tenant or "").strip()
