"""Safe error logging for identity endpoints (merge review E2 and merge review 2, E2 scope).

Used by the identity-sync endpoints, the Keycloak callback and the back-channel logout. Their requests carry
personal data or secrets: the subject, e-mail addresses, the authorization code, `state` and logout tokens.
"""

import functools
import json

import frappe
from frappe import _

from platform_core.identity.exceptions import IdentityInternalError

# Merge review E2: these request fields identify a person or carry a secret. They never reach a log.
PERSONAL_FIELDS = (
	"subject",
	"email",
	"new_email",
	"first_name",
	"last_name",
	"logout_token",
	"code",
	"state",
	"error_description",
)
REDACTED = "[REDACTED]"


def safe_errors(fn):
	"""Server errors of identity, sign-in and logout endpoints keep personal data out of the Error Log, the app log and the response.

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
			if getattr(error, "expected_outage", False) and type(error).__module__.startswith(
				"platform_core"
			):
				# An expected outage of a service the site calls (AJA-459). The caller logged it without data.
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
				_("The identity endpoint failed.", context="platform_core.identity")
			) from None

	return wrapper
