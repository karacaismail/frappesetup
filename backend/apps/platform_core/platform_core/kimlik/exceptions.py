"""Error classes of the identity endpoints. `http_status_code` sets the HTTP status (frappe/app.py:363).

Clients read the `exc_type` field of the response. The class names are listed in the OpenAPI contract.
"""

import frappe


class InvalidRedirect(frappe.ValidationError):
	http_status_code = 400


class KeycloakSettingsMissing(frappe.ValidationError):
	http_status_code = 400


class InvalidInput(frappe.ValidationError):
	http_status_code = 400


class PayloadTooLarge(frappe.ValidationError):
	http_status_code = 413


class KeycloakLoginNotConfigured(frappe.ValidationError):
	http_status_code = 503


class KeycloakKeysUnavailable(frappe.ValidationError):
	"""Expected outage of the identity provider. Frappe snapshots 5xx errors together with the request
	body (frappe/app.py:428); `skip_error_log` keeps personal data of identity requests out of Error Log.
	The module writes its own data-free log entry instead."""

	http_status_code = 503
	skip_error_log = True


class InvalidLogoutToken(frappe.ValidationError):
	http_status_code = 400


class ServiceTokenRejected(frappe.AuthenticationError):
	http_status_code = 401


class UnknownIssuer(frappe.ValidationError):
	http_status_code = 400


class DeskRoleNotAllowed(frappe.ValidationError):
	http_status_code = 400


class EmailMismatch(frappe.ValidationError):
	http_status_code = 409


class EmailNotVerified(frappe.ValidationError):
	http_status_code = 409


class IdentityConflict(frappe.ValidationError):
	http_status_code = 409


class EmailInUse(frappe.ValidationError):
	http_status_code = 409


class IdentityNotFound(frappe.DoesNotExistError):
	http_status_code = 404


class IdentityDeleted(frappe.ValidationError):
	"""The identity `(iss, sub)` was deleted (O-27). It cannot be provisioned, enabled or renamed again."""

	http_status_code = 410


class DeletionKeyMissing(frappe.ValidationError):
	"""The site setting `kimlik_deletion_hmac_key` is missing. Identity changes fail closed."""

	http_status_code = 503
