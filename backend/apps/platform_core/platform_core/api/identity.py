"""identity-sync endpoints. Only the `identity-sync` service token is accepted (docs/sozlesmeler.md, section 5).

Parameters carry no type hints on purpose: Frappe would answer a wrong type with its own 417 before the
module runs. `provisioning` validates every field and answers 400 `InvalidInput` (the contract's single shape)."""

import frappe

from platform_core.kimlik import anonymization, provisioning, service_token, sign_in

SERVICE = "identity-sync"


@frappe.whitelist(methods=["POST"])
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
def set_enabled(issuer=None, subject=None, enabled=None) -> dict:
	"""Enables or disables the user. Disabling closes all of the user's sessions."""
	service_token.require_service(SERVICE)
	return provisioning.set_enabled({"issuer": issuer, "subject": subject, "enabled": enabled})


@frappe.whitelist(methods=["POST"])
def change_email(issuer=None, subject=None, new_email=None) -> dict:
	"""Changes the e-mail with `rename_doc`. The identity link follows the user."""
	service_token.require_service(SERVICE)
	return provisioning.change_email({"issuer": issuer, "subject": subject, "new_email": new_email})


@frappe.whitelist(methods=["POST"])
def anonymize_user(issuer=None, subject=None) -> dict:
	"""Disables the user and anonymizes the person. Business records stay (O-27). Irreversible."""
	service_token.require_service(SERVICE)
	sign_in.guard_guest_request()
	return anonymization.anonymize_user({"issuer": issuer, "subject": subject})
