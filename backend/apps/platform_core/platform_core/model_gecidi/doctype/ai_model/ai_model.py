import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from platform_core.model_gecidi.doctype.validation import encode_identifiers


class AIModel(Document):
	def validate(self):
		self.capabilities = encode_identifiers(self.capabilities, "Capabilities")
		if cint(self.context_size) < 1:
			frappe.throw(_("Context size must be at least 1 token."))
		if cint(self.output_tokens_per_second) < 1:
			frappe.throw(_("Output speed must be at least 1 token per second."))
