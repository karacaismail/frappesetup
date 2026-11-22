import json

import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.model_gateway.doctype.validation import encode_identifiers, parse_records


class AIRoute(Document):
	def validate(self):
		self.required_capabilities = encode_identifiers(self.required_capabilities, "Required Capabilities")
		targets = parse_records(self.targets, "Targets", required=True)
		seen = set()
		for target in targets:
			if not isinstance(target, dict) or set(target) != {"model", "api"}:
				frappe.throw(_("Each target must contain one model and one API connection."))
			model, api = target["model"], target["api"]
			if any(not isinstance(name, str) or not name or name != name.strip() for name in (model, api)):
				frappe.throw(_("Each target must use valid model and API document names."))
			if (model, api) in seen:
				frappe.throw(_("Each model and API pair may appear only once."))
			seen.add((model, api))
		self.targets = json.dumps(targets, separators=(",", ":"))
