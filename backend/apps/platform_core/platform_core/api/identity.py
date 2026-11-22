"""identity-sync endpoints. Only the `identity-sync` service token is accepted (docs/sozlesmeler.md, section 5).

Parameters carry no type hints on purpose: Frappe would answer a wrong type with its own 417 before the
module runs. `provisioning` validates every field and answers 400 `InvalidInput` (the contract's single shape)."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.kimlik import anonymization, provisioning, service_token, sign_in
from platform_core.kimlik.exceptions import InvalidInput

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


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
def provision(
	issuer=None,
	subject=None,
	email=None,
	email_verified=None,
	first_name=None,
	last_name=None,
	enabled=None,
	role_profiles=None,
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
def set_enabled(issuer=None, subject=None, enabled=None) -> dict:
	"""Enables or disables the user. Disabling closes all of the user's sessions."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "enabled")
	return provisioning.set_enabled({"issuer": issuer, "subject": subject, "enabled": enabled})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
def change_email(issuer=None, subject=None, new_email=None) -> dict:
	"""Changes the e-mail with `rename_doc`. The identity link follows the user."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "new_email")
	return provisioning.change_email({"issuer": issuer, "subject": subject, "new_email": new_email})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
def anonymize_user(issuer=None, subject=None) -> dict:
	"""Disables the user and anonymizes the person. Business records stay (O-27). Irreversible."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject")
	sign_in.guard_guest_request()
	return anonymization.anonymize_user({"issuer": issuer, "subject": subject})
