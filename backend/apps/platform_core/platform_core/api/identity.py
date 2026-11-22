"""identity-sync endpoints. Only the `identity-sync` service token is accepted (docs/sozlesmeler.md, section 5).

Parameters carry no type hints on purpose: Frappe would answer a wrong type with its own 417 before the
module runs. `provisioning` validates every field and answers 400 `InvalidInput` (the contract's single shape)."""

import functools
import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from platform_core.kimlik import anonymization, provisioning, service_token, sign_in
from platform_core.kimlik.exceptions import IdentityInternalError, InvalidInput

SERVICE = "identity-sync"
# identity-sync is one client. The limit leaves room for a reconciliation run (G-7, S-GIR-4).
SERVICE_LIMIT = 300
SERVICE_WINDOW = 60


# Merge review E2: these request fields identify a person or carry a secret. They never reach a log.
PERSONAL_FIELDS = ("subject", "email", "new_email", "first_name", "last_name", "logout_token")
REDACTED = "[REDACTED]"


def _safe_errors(fn):
	"""Server errors of identity endpoints keep personal data out of the Error Log, the app log and the response.

	Frappe writes the request fields and a traceback with local values for every 5xx error
	(frappe/app.py:428, frappe/utils/error.py:61 and :74). Its own filter hides only password-like
	names (frappe/utils/logger.py:119). This wrapper redacts the personal fields first, writes one Error Log
	entry with safe fields only, and stops Frappe's own snapshot (`skip_error_log`).
	Known safe errors keep their type and message. Any other error becomes `IdentityInternalError`.
	"""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except Exception as error:
			status = getattr(error, "http_status_code", 500)
			if status < 500:
				raise
			for field in PERSONAL_FIELDS:
				if field in frappe.form_dict:
					frappe.form_dict[field] = REDACTED
			frappe.log_error(
				title=f"Identity endpoint failed: {fn.__name__}",
				message=json.dumps(
					{"endpoint": fn.__name__, "error": type(error).__name__, "status": status}
				),
			)
			if isinstance(error, frappe.ValidationError) and type(error).__module__.startswith(
				"platform_core"
			):
				error.skip_error_log = True
				raise
			raise IdentityInternalError(
				_("The identity endpoint failed.", context="platform_core.kimlik")
			) from None

	return wrapper


def _only(*fields: str) -> None:
	"""S-API-3: the contract says `additionalProperties: false`. Unknown body fields are refused."""
	unknown = sorted(set(frappe.form_dict) - set(fields) - {"cmd"})
	if unknown:
		frappe.throw(
			_("Unknown field: {0}", context="platform_core.kimlik").format(", ".join(unknown)), InvalidInput
		)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@_safe_errors
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
@_safe_errors
def set_enabled(issuer=None, subject=None, enabled=None) -> dict:
	"""Enables or disables the user. Disabling closes all of the user's sessions."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "enabled")
	return provisioning.set_enabled({"issuer": issuer, "subject": subject, "enabled": enabled})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@_safe_errors
def change_email(issuer=None, subject=None, new_email=None) -> dict:
	"""Changes the e-mail with `rename_doc`. The identity link follows the user."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject", "new_email")
	return provisioning.change_email({"issuer": issuer, "subject": subject, "new_email": new_email})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=SERVICE_LIMIT, seconds=SERVICE_WINDOW, user_based=True)
@_safe_errors
def anonymize_user(issuer=None, subject=None) -> dict:
	"""Disables the user and anonymizes the person. Business records stay (O-27). Irreversible."""
	service_token.require_service(SERVICE)
	_only("issuer", "subject")
	sign_in.guard_guest_request()
	return anonymization.anonymize_user({"issuer": issuer, "subject": subject})
