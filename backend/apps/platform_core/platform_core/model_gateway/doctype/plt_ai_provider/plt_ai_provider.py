import frappe
from frappe import _
from frappe.model.document import Document
from pypika.functions import Coalesce

from platform_core.model_gateway.doctype.validation import validate_url


class PLTAIProvider(Document):
	def validate(self):
		validate_url(self.default_url, "Default Base URL")
		if not self.get_doc_before_save():
			return
		adapter_changed = self.has_value_changed("adapter")
		url_changed = self.has_value_changed("default_url")
		if not (adapter_changed or url_changed):
			return

		api = frappe.qb.DocType("PLT AI API")
		account = frappe.qb.DocType("PLT AI Account")
		query = (
			frappe.qb.from_(api)
			.join(account)
			.on(api.account == account.name)
			.select(api.name)
			.where(account.provider == self.name)
			.where(Coalesce(api.api_key, "") != "")
		)
		if not adapter_changed:
			query = query.where(Coalesce(api.base_url, "") == "")
		if query.limit(1).for_update().run():
			frappe.throw(_("Clear the affected API credentials before changing the provider destination."))
