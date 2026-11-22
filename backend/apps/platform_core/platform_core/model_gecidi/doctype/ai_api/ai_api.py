import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from platform_core.model_gecidi.doctype.validation import encode_identifiers


class AIAPI(Document):
	def validate(self):
		self.allowed_models = encode_identifiers(self.allowed_models, "Allowed Models")
		if self.api_key and not isinstance(self.api_key, str):
			frappe.throw(_("Enter the API credential as text."))
		if self.is_new() and self.api_key and self.is_dummy_password(self.api_key):
			frappe.throw(_("Enter a credential without using the password mask."))
		if not cint(self.enabled):
			return
		if self.auth_type != "none" and not self.api_key:
			frappe.throw(_("Enter a credential for the enabled API connection."))
		if self.auth_type == "oauth_client_credentials" and (
			not self.oauth_client_id or not self.oauth_token_url
		):
			frappe.throw(_("Enter the OAuth client ID and token URL."))

	def as_dict(self, *args, **kwargs):
		data = super().as_dict(*args, **kwargs)
		data.pop("api_key", None)
		return data
