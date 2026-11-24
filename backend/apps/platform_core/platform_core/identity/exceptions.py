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


class IdentityInternalError(frappe.ValidationError):
	"""An unexpected server error of an identity endpoint. The message carries no request data (review E2)."""

	http_status_code = 500
	skip_error_log = True


class IdentityLinkMissing(frappe.PermissionError):
	"""The session has no Keycloak subject that matches the identity link of the signed-in user (AJA-459).

	The site then sends no request to identity-sync. The message names no person."""

	http_status_code = 403


class LinkedAccountsForbidden(frappe.PermissionError):
	"""identity-sync refused the read. The person is unknown or belongs to another tenant (AJA-459).

	Both cases give the same answer, so the reply does not tell whether a person exists."""

	http_status_code = 403


class IdentityServiceUnavailable(frappe.ValidationError):
	"""identity-sync or Keycloak did not answer, or the answer was not usable (AJA-459).

	The message carries no secret, no token and no internal address."""

	http_status_code = 503
	skip_error_log = True
