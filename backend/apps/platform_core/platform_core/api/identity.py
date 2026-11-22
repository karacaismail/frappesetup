"""identity-sync endpoints. Only the `identity-sync` service token is accepted (docs/sozlesmeler.md, section 5).

Parameters are typed `object` (G-8): Frappe's type check then accepts every value, and `provisioning`
validates each field itself and answers 400 `InvalidInput` (the contract's single shape). A narrower hint
would let Frappe answer a wrong type with its own 417 first."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.kimlik import anonymization, provisioning, service_token, sign_in
from platform_core.kimlik.exceptions import InvalidInput
from platform_core.kimlik.reconciliation import list_linked_identities
from platform_core.kimlik.safe_errors import safe_errors

SERVICE = "identity-sync"
# identity-sync is one client. The limit leaves room for a reconciliation run (G-7, S-GIR-4).
SERVICE_LIMIT = 300
SERVICE_WINDOW = 60


def _only(*fields: str) -> None:
	"""S-API-3: the contract says `additionalProperties: false`. Unknown body fields are refused."""
	unknown = sorted(set(frappe.form_dict) - set(fields) - {"cmd"})
	if unknown:
		frappe.throw(
			_("Unknown field: {0}", context="platform_core.kimlik").format(", ".join(unknown)), InvalidInput
		)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def list_identities(start: object = 0, page_length: object = 500) -> dict:
	"""Lists a page of linked identities for the identity-sync service."""
	service_token.require_service(SERVICE)
	_only("start", "page_length")
	return list_linked_identities(start, page_length)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def provision(
	issuer: object = None,
	subject: object = None,
	email: object = None,
	email_verified: object = None,
	first_name: object = None,
	last_name: object = None,
	enabled: object = None,
	role_profiles: object = None,
) -> dict:
	"""Creates or updates the user. The same request returns the same result twice."""
	service_token.require_service(SERVICE)
	_only(
		"issuer", "subject", "email", "email_verified", "first_name", "last_name", "enabled", "role_profiles"
	)
	return provisioning.provision(
		{
			"issuer": issuer,
			"subject": subject,
			"email": email,
			"email_verified": email_verified,
			"first_name": first_name,
			"last_name": last_name,
			"enabled": enabled,
			"role_profiles": role_profiles,
		}
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def set_enabled(issuer: object = None, subject: object = None, enabled: object = None) -> dict:
	"""Enables or disables the user. Disabling closes all of the user's sessions."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "enabled")
	return provisioning.set_enabled({"issuer": issuer, "subject": subject, "enabled": enabled})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def change_email(issuer: object = None, subject: object = None, new_email: object = None) -> dict:
	"""Changes the e-mail with `rename_doc`. The identity link follows the user."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "new_email")
	return provisioning.change_email({"issuer": issuer, "subject": subject, "new_email": new_email})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def anonymize_user(issuer: object = None, subject: object = None) -> dict:
	"""Disables the user and anonymizes the person. Business records stay (O-27). Irreversible."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject")
	sign_in.guard_guest_request()
	return anonymization.anonymize_user({"issuer": issuer, "subject": subject})
