"""identity-sync endpoints. Only the `identity-sync` service token is accepted (docs/sozlesmeler.md, section 5).

The two user management endpoints at the end are different: the panel calls them with the
session of a “System Manager” or a “Tenant Admin” (G-98).

Parameters are typed `object` (G-8): Frappe's type check then accepts every value, and `provisioning`
validates each field itself and answers 400 `InvalidInput` (the contract's single shape). A narrower hint
would let Frappe answer a wrong type with its own 417 first."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.identity import anonymization, provisioning, service_token, sign_in, user_admin
from platform_core.identity.exceptions import InvalidInput
from platform_core.identity.reconciliation import list_linked_identities
from platform_core.identity.safe_errors import safe_errors

SERVICE = "identity-sync"
# identity-sync is one client. The limit leaves room for a reconciliation run (G-7, S-GIR-4).
SERVICE_LIMIT = 300
SERVICE_WINDOW = 60
# A manager may send this many invitation requests in the window (AJA-890). A preview and its run
# are two requests, so this is ten invitations in ten minutes. The counter belongs to the user.
INVITE_LIMIT = 20
INVITE_WINDOW = 600


def _only(*fields: str) -> None:
	"""S-API-3: the contract says `additionalProperties: false`. Unknown body fields are refused."""
	unknown = sorted(set(frappe.form_dict) - set(fields) - {"cmd"})
	if unknown:
		frappe.throw(
			_("Unknown field: {0}", context="platform_core.identity").format(", ".join(unknown)), InvalidInput
		)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def list_identities(start: object = 0, page_length: object = 500) -> dict:
	"""Lists a page of linked identities for the identity-sync service."""
	service_token.require_service(SERVICE)
	if not frappe.has_permission(provisioning.LINK, "read"):
		frappe.throw(
			_("You do not have permission to read identity links.", context="platform_core.identity"),
			frappe.PermissionError,
		)
	_only("start", "page_length")
	return list_linked_identities(start, page_length)


# The verified site-scoped service claim authorizes the internal identity operations.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
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


# The verified site-scoped service claim authorizes the internal identity operations.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def set_enabled(issuer: object = None, subject: object = None, enabled: object = None) -> dict:
	"""Enables or disables the user. Disabling closes all of the user's sessions."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "enabled")
	return provisioning.set_enabled({"issuer": issuer, "subject": subject, "enabled": enabled})


# The verified site-scoped service claim authorizes the internal identity operations.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def change_email(issuer: object = None, subject: object = None, new_email: object = None) -> dict:
	"""Changes the e-mail with `rename_doc`. The identity link follows the user."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "new_email")
	return provisioning.change_email({"issuer": issuer, "subject": subject, "new_email": new_email})


# The verified site-scoped service claim authorizes the internal identity operations.
@frappe.whitelist(methods=["POST"])  # nosemgrep: frappe-missing-permission
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@safe_errors
def anonymize_user(issuer: object = None, subject: object = None) -> dict:
	"""Disables the user and anonymizes the person. Business records stay (O-27). Irreversible."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject")
	sign_in.guard_guest_request()
	return anonymization.anonymize_user({"issuer": issuer, "subject": subject})


# --- user management of the panel (G-98). The session's role is checked in `user_admin`. ---


@frappe.whitelist(methods=["POST"])
def set_user_role_profiles(user: object = None, role_profiles: object = None) -> dict:
	"""Gives a user of this tenant exactly these role profiles (G-98).

	“System Manager” and “Tenant Admin” only. A profile with a protected or desk role is refused.
	"""
	_only("user", "role_profiles")
	return user_admin.set_user_role_profiles(user, role_profiles)


@frappe.whitelist(methods=["GET"])
def get_user_role_profiles(user: object = None) -> dict:
	"""The role profiles and the roles of a user of this tenant (G-98, AJA-913).

	“System Manager” and “Tenant Admin” only. No other field of the user is given.
	"""
	_only("user")
	return user_admin.get_user_role_profiles(user)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=INVITE_LIMIT, seconds=INVITE_WINDOW, user_based=True)
def invite_user(
	email: object = None,
	first_name: object = None,
	last_name: object = None,
	dry_run: object = None,
	preview_digest: object = None,
) -> dict:
	"""Previews or runs the invitation of a person into this tenant (G-16, G-79, G-98).

	“System Manager” and “Tenant Admin” only. The run needs the digest of its preview.
	Too many requests of one user in a short time get 429.
	"""
	_only("email", "first_name", "last_name", "dry_run", "preview_digest")
	return user_admin.invite_user(email, first_name, last_name, dry_run, preview_digest)
