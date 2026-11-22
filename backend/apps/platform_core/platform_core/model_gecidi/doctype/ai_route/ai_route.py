import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.model_gecidi.doctype.validation import encode_identifiers


class AIRoute(Document):
	def validate(self):
		if self.data_policy == "masked" and self.has_value_changed("data_policy"):
			frappe.only_for("AI Manager", message=True)
		self.required_capabilities = encode_identifiers(self.required_capabilities, "Required Capabilities")
		if not self.targets:
			frappe.throw(_("Add at least one model and API target."))
		seen = set()
		for target in self.targets:
			model, api = target.model, target.api
			if any(not isinstance(name, str) or not name or name != name.strip() for name in (model, api)):
				frappe.throw(_("Each target must use valid model and API document names."))
			if (model, api) in seen:
				frappe.throw(_("Each model and API pair may appear only once."))
			seen.add((model, api))
