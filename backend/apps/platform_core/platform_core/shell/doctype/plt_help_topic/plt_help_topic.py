"""The “Help Topic” record: help content linked to a field, component or route (G-138)."""

import frappe
from frappe import _
from frappe.model.document import Document

from platform_core.shell.help_content import FIELD, HELP_URL_FIELDS, is_safe_help_url, target_errors

MESSAGES = {
	"document_type": "Select the document type of the field.",
	"fieldname": "Enter the field name.",
	"field_missing": "Field {1} does not exist in {0}.",
	"custom_field_layer": "Help on custom field {1} of {0} must be tenant content.",
	"component_id": "Enter the component identifier.",
	"route_pattern": "Enter the route pattern.",
	"target_type": "Select a valid target type.",
}


class PLTHelpTopic(Document):
	def validate(self):
		for fieldname in HELP_URL_FIELDS:
			value = self.get(fieldname)
			if not is_safe_help_url(value):
				frappe.throw(
					_("Help links must use HTTPS or a same-site relative path."), frappe.ValidationError
				)
			self.set(fieldname, value.strip() or None if value else None)
		field = None
		if self.target_type == FIELD and self.document_type and self.fieldname:
			if frappe.db.exists("DocType", self.document_type):
				field = frappe.get_meta(self.document_type).get_field(self.fieldname)
		errors = target_errors(
			self.as_dict(),
			field_exists=field is not None,
			field_is_custom=bool(field and field.get("is_custom_field")),
		)
		if errors:
			frappe.throw(
				_(MESSAGES[errors[0]]).format(frappe.bold(self.document_type), frappe.bold(self.fieldname)),
				frappe.ValidationError,
			)
		if self.target_type == FIELD:
			# The version of a field's help is compared with this application's version.
			self.app = frappe.get_doctype_app(self.document_type)
