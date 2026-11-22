from frappe.model.document import Document

from platform_core.model_gecidi.doctype.validation import validate_url


class AIProvider(Document):
	def validate(self):
		validate_url(self.default_url, "Default Base URL")
