"""G-98: the “Tenant Admin” invites users and gives them role profiles.

A tenant is its own Frappe site. A user of the tenant is a Website User with an identity link
to the site's Keycloak issuer. Any other user (a user of another tenant, a desk user or a missing
user) gets the same 403, so the answer does not tell whether a person exists.

Invitation (G-16, G-79): the site calls identity-sync `/v1/invitations` with its own service token.
identity-sync creates the Keycloak user, adds the user to the tenant's organization and sends the
password e-mail. The organization comes from the site config (`keycloak_organization_id`), never
from the request. identity-sync checks again that the organization is the tenant's own.
The flow has two steps. The first call is a preview (`dry_run: true`) and only reads. The person
looks at the preview in the panel. The second call carries the preview's digest: this call is the
person's approval. The site gives it a new approval id. identity-sync runs only the approved plan.
The Website User of the invited person is made when the person signs in for the first time.

The access module may not be imported here (`dev/module-boundaries.json`). Its guards still run on
every user save (`tenant_admin.guard_user`): the two protected roles and roles that are not plain
are never given. This module refuses a profile with a desk role before the save.
"""

import re
import uuid

import frappe
from frappe import _
from frappe.utils import validate_email_address

from platform_core.identity import site_settings
from platform_core.identity.exceptions import (
	IdentityConflict,
	IdentityServiceUnavailable,
	InvalidInput,
)
from platform_core.identity.login_accounts import _TRANSPORT_ERRORS, _identity_sync_origin, _send
from platform_core.identity.service_client import identity_sync_bearer, invalidate_identity_sync_bearer

LINK = "PLT Identity Link"
WEBSITE_USER = "Website User"
# The role that `tenant_admin.ROLE` of the access module names (G-62).
TENANT_ADMIN = "Tenant Admin"
PROTECTED_ROLES = frozenset({"Administrator", "System Manager"})
INVITATIONS_PATH = "/v1/invitations"
MAX_NAME = 150
MAX_EMAIL = 254
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,189}")
_RESOURCE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class InvitationChanged(frappe.ValidationError):
	"""The plan changed after the preview. A new preview is needed."""

	http_status_code = 409


def require_manager() -> None:
	"""A System Manager or a “Tenant Admin” manages the tenant's users. Nobody else does."""
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles & {"System Manager", TENANT_ADMIN}:
		frappe.throw(
			_("No permission to manage users.", context="platform_core.identity"), frappe.PermissionError
		)


def _deny(message: str) -> None:
	frappe.throw(message, frappe.PermissionError, title=_("Not allowed", context="platform_core.identity"))


def _deny_user() -> None:
	_deny(_("This user is not a user of this tenant.", context="platform_core.identity"))


def tenant_user(user: object) -> str:
	"""The user, if the user is a Website User linked to this tenant. Otherwise 403."""
	if not isinstance(user, str) or not user or user in ("Administrator", "Guest"):
		_deny_user()
	# A system check of the target user (exception to G-3). The caller was checked before.
	if frappe.db.get_value("User", user, "user_type") != WEBSITE_USER:
		_deny_user()
	if not frappe.db.exists(LINK, {"issuer": site_settings.issuer(), "user": user}):
		_deny_user()
	return user


def _profile_names(value: object) -> list[str]:
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.strip().startswith("[") else value
	if not isinstance(value, list) or not all(isinstance(name, str) and name.strip() for name in value):
		frappe.throw(
			_("role_profiles must be a list of role profile names.", context="platform_core.identity"),
			InvalidInput,
		)
	names = sorted({name.strip() for name in value})
	for name in names:
		if not frappe.db.exists("Role Profile", name):
			frappe.throw(
				_("Role profile {0} not found.", context="platform_core.identity").format(name),
				frappe.DoesNotExistError,
			)
	return names


def set_user_role_profiles(user: object, role_profiles: object) -> dict:
	"""Gives a tenant user exactly these role profiles. The user's roles follow the profiles.

	Frappe keeps the roles when the list is empty: only the profile links go.
	"""
	require_manager()
	names = _profile_names(role_profiles)
	user = tenant_user(user)
	# The profile roles are system data (exception to G-3).
	roles = set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "Role Profile", "parent": ("in", names or [""])},
			pluck="role",
			limit=0,
		)
	)
	if roles & PROTECTED_ROLES:
		_deny(
			_(
				"Only a System Manager can give a role profile with the System Manager or Administrator role.",
				context="platform_core.identity",
			)
		)
	# G-16: a panel user never gets a role with desk access.
	desk = frappe.get_all(
		"Role", filters={"name": ("in", sorted(roles) or [""]), "desk_access": 1}, pluck="name", limit=1
	)
	if desk:
		_deny(
			_("Only a System Manager can give the role {0}.", context="platform_core.identity").format(
				desk[0]
			)
		)
	doc = frappe.get_doc("User", user)
	doc.set("role_profiles", [{"role_profile": name} for name in names])
	# The caller's right was checked above. `guard_user` of the access module still runs on save.
	doc.flags.ignore_permissions = True
	doc.save()
	return {
		"user": doc.name,
		"role_profiles": [row.role_profile for row in doc.role_profiles],
		"roles": sorted(row.role for row in doc.roles),
	}


# --- invitation ---


def _unavailable(reason: str) -> IdentityServiceUnavailable:
	# The log names the reason. It never names the person, the address or the token.
	frappe.logger("platform_core.identity").warning("invitation failed: outcome=%s", reason)
	return IdentityServiceUnavailable(
		_("The invitation service is not available. Try again later.", context="platform_core.identity")
	)


def _organization() -> str:
	value = frappe.conf.get("keycloak_organization_id")
	if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
		raise _unavailable("not_configured")
	return value


def _call(payload: dict) -> object:
	"""Calls identity-sync once. A rejected token is dropped and the call is tried once more."""
	try:
		url = _identity_sync_origin() + INVITATIONS_PATH
		bearer = identity_sync_bearer()
	except _TRANSPORT_ERRORS:
		raise _unavailable("not_configured") from None
	failure = "no_answer"
	for attempt in range(2):
		try:
			status, body = _send("POST", url, payload, bearer)
		except _TRANSPORT_ERRORS:
			break
		if status == 200:
			return body
		if status == 403:
			frappe.throw(
				_("This site cannot invite into this organization.", context="platform_core.identity"),
				frappe.PermissionError,
			)
		if status == 409:
			frappe.throw(
				_(
					"The invitation changed after the preview. Preview it again.",
					context="platform_core.identity",
				),
				InvitationChanged,
			)
		if status == 400:
			frappe.throw(
				_("The invitation service refused the invitation fields.", context="platform_core.identity"),
				InvalidInput,
			)
		failure = f"status_{status}"
		if status != 401 or attempt:
			break
		invalidate_identity_sync_bearer(bearer)
		try:
			bearer = identity_sync_bearer()
		except _TRANSPORT_ERRORS:
			failure = "token_refused"
			break
	raise _unavailable(failure)


def _name(value: object, field: str) -> str:
	if value in (None, ""):
		return ""
	if not isinstance(value, str) or len(value) > MAX_NAME:
		frappe.throw(
			_("{0} must be a text of at most {1} characters.", context="platform_core.identity").format(
				field, MAX_NAME
			),
			InvalidInput,
		)
	return value.strip()


def _flag(value: object) -> bool:
	"""`dry_run` must be written. JSON gives true and false. A form gives "1" and "0"."""
	if isinstance(value, bool):
		return value
	if value in ("1", "true", 1):
		return True
	if value in ("0", "false", 0):
		return False
	frappe.throw(_("dry_run must be true or false.", context="platform_core.identity"), InvalidInput)


def _previews(value: object) -> list[dict]:
	if not isinstance(value, list):
		raise _unavailable("invalid_reply")
	rows = []
	for row in value:
		if isinstance(row, dict) and isinstance(row.get("operation"), str):
			rows.append({key: row[key] for key in ("operation", "target", "destructive") if key in row})
	return rows


def invite_user(
	email: object,
	first_name: object = None,
	last_name: object = None,
	dry_run: object = None,
	preview_digest: object = None,
) -> dict:
	"""Previews or runs the invitation of one person into the tenant's organization."""
	require_manager()
	if not isinstance(email, str) or len(email) > MAX_EMAIL or not _EMAIL.fullmatch(email.strip()):
		frappe.throw(_("email must be an e-mail address.", context="platform_core.identity"), InvalidInput)
	email = email.strip().lower()
	if not validate_email_address(email):
		frappe.throw(_("email must be an e-mail address.", context="platform_core.identity"), InvalidInput)
	run = not _flag(dry_run)
	if run and (not isinstance(preview_digest, str) or not _DIGEST.fullmatch(preview_digest)):
		frappe.throw(
			_("A run needs the preview_digest of its preview.", context="platform_core.identity"),
			InvalidInput,
		)
	first, last = _name(first_name, "first_name"), _name(last_name, "last_name")
	# G-16: a desk account is never made a panel user (exception to G-3: a system check).
	user_type = frappe.db.get_value("User", {"name": email}, "user_type")
	if user_type and user_type != WEBSITE_USER:
		frappe.throw(
			_("This e-mail belongs to a desk user and cannot be invited.", context="platform_core.identity"),
			IdentityConflict,
		)
	payload = {"email": email}
	if first:
		payload["first_name"] = first
	if last:
		payload["last_name"] = last
	payload.update({"organization_id": _organization(), "dry_run": not run})
	if run:
		# The person's second call is the approval. Each run has a new, single-use approval id.
		approval = "tenant-admin-" + uuid.uuid4().hex
		payload.update({"preview_digest": preview_digest, "approval_id": approval})
	reply = _call(payload)
	if not isinstance(reply, dict):
		raise _unavailable("invalid_reply")
	subject = reply.get("subject")
	if subject is not None and (not isinstance(subject, str) or len(subject) > 128):
		raise _unavailable("invalid_reply")
	result = {"dry_run": not run, "subject": subject, "previews": _previews(reply.get("previews"))}
	if run:
		frappe.logger("platform_core.identity").info("invitation executed: approval=%s", approval)
		return result
	digest = reply.get("preview_digest")
	if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
		raise _unavailable("invalid_reply")
	return {**result, "preview_digest": digest}
