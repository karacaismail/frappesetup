import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint
from frappe.utils.password import remove_encrypted_password

from platform_core.model_gateway.doctype.validation import encode_identifiers, validate_url


class PLTAIAPI(Document):
	def validate(self):
		self.allowed_models = encode_identifiers(self.allowed_models, "Allowed Models", self.doctype)
		validate_url(self.base_url, "Base URL", self.doctype)
		validate_url(self.oauth_token_url, "OAuth Token URL", self.doctype, https_only=True)
		if self.api_key and not isinstance(self.api_key, str):
			frappe.throw(_("Enter the API credential as text."))
		uses_mask = self.api_key and self.is_dummy_password(self.api_key)
		if not self.api_key or uses_mask:
			previous = self.get_doc_before_save()
			saved_marker = previous.get("api_key") if previous else None
			if isinstance(saved_marker, str) and self.is_dummy_password(saved_marker):
				# Frappe preserves the encrypted value when the stored mask is submitted.
				self.api_key = saved_marker
			elif uses_mask:
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

	def get_password(self, fieldname="password", raise_exception=True):
		# The native Frappe RPC dispatches through this method on the lazy controller.
		frappe.throw(_("API credentials cannot be read through document methods."), frappe.PermissionError)


def clear_api_credential(name):
	"""Explicitly remove an encrypted credential from a disabled connection."""
	api = frappe.get_doc("PLT AI API", name, for_update=True)
	api.check_permission("write")
	if api.enabled:
		frappe.throw(_("Disable the API connection before clearing its credential."))
	remove_encrypted_password(api.doctype, api.name, "api_key")
	api.db_set("api_key", None, update_modified=False)
