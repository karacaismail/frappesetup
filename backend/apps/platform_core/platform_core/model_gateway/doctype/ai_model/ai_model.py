from frappe.model.document import Document

from platform_core.model_gateway.doctype.validation import encode_identifiers


class AIModel(Document):
	def validate(self):
		self.capabilities = encode_identifiers(self.capabilities, "Capabilities")
