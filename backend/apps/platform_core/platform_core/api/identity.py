"""identity-sync endpoints. Only the `identity-sync` service token is accepted (docs/sozlesmeler.md, section 5)."""

import frappe

from platform_core.kimlik import provisioning, service_token

SERVICE = "identity-sync"


@frappe.whitelist(methods=["POST"])
def provision(
	issuer: str | None = None,
	subject: str | None = None,
	email: str | None = None,
	email_verified: bool | str | int | None = None,
	first_name: str | None = None,
	last_name: str | None = None,
	enabled: bool | str | int | None = None,
	role_profiles: list | str | None = None,
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
def set_enabled(
	issuer: str | None = None, subject: str | None = None, enabled: bool | str | int | None = None
) -> dict:
	"""Enables or disables the user. Disabling closes all of the user's sessions."""
	service_token.require_service(SERVICE)
	return provisioning.set_enabled({"issuer": issuer, "subject": subject, "enabled": enabled})


@frappe.whitelist(methods=["POST"])
def change_email(issuer: str | None = None, subject: str | None = None, new_email: str | None = None) -> dict:
	"""Changes the e-mail with `rename_doc`. The identity link follows the user."""
	service_token.require_service(SERVICE)
	return provisioning.change_email({"issuer": issuer, "subject": subject, "new_email": new_email})
