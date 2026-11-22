from frappe.model.document import Document

from platform_core.model_gecidi.doctype.validation import encode_identifiers


class AIModel(Document):
	def validate(self):
		self.capabilities = encode_identifiers(self.capabilities, "Capabilities")
