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


class KeycloakLoginNotConfigured(frappe.ValidationError):
	http_status_code = 503


class KeycloakKeysUnavailable(frappe.ValidationError):
	http_status_code = 503


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
