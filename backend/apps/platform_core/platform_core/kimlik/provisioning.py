"""User provisioning for identity-sync: create, enable or disable, change e-mail (docs/sozlesmeler.md, section 5).

The caller runs as the administrator through the service token (service_token.validate). Every
operation is repeatable: the same request returns the same body twice. New users are “Website User”
(D-5, G-16).
"""

import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc
from frappe.utils import validate_email_address

from platform_core.kimlik import sign_in, site_settings
from platform_core.kimlik.exceptions import (
	DeskRoleNotAllowed,
	EmailInUse,
	EmailMismatch,
	EmailNotVerified,
	IdentityConflict,
	IdentityNotFound,
	InvalidInput,
	UnknownIssuer,
)

LINK = "Platform Identity Link"
WEBSITE_USER = "Website User"
MAX_SUBJECT = 140
MAX_ISSUER = 255


def provision(data: dict) -> dict:
	issuer = _issuer(data)
	subject = _text(data, "subject", MAX_SUBJECT)
	email = _email(data.get("email"))
	email_verified = _bool(data, "email_verified")
	enabled = _bool(data, "enabled")
	first_name = _optional_text(data, "first_name")
	last_name = _optional_text(data, "last_name")
	role_profiles = _role_profiles(data.get("role_profiles"))

	user = _linked_user(issuer, subject)
	if user:
		if user != email:
			frappe.throw(
				_("E-mail differs from the linked user. Use change_email.", context="platform_core.kimlik"),
				EmailMismatch,
			)
		doc = frappe.get_doc("User", user)
	else:
		if not email_verified:
			frappe.throw(
				_("The first link requires a verified e-mail address.", context="platform_core.kimlik"),
				EmailNotVerified,
			)
		if frappe.db.exists(LINK, {"issuer": issuer, "user": email}):
			frappe.throw(
				_("This e-mail is already linked to a different identity.", context="platform_core.kimlik"),
				IdentityConflict,
			)
		if frappe.db.exists("User", email):
			doc = frappe.get_doc("User", email)
			# End-user provisioning never takes over a desk account (O-3 in the security review).
			if doc.user_type != WEBSITE_USER or doc.has_desk_access():
				frappe.throw(
					_(
						"This e-mail belongs to a desk user and cannot be provisioned.",
						context="platform_core.kimlik",
					),
					IdentityConflict,
				)
		else:
			doc = frappe.new_doc("User")
			doc.update({"email": email, "user_type": WEBSITE_USER, "send_welcome_email": 0})
			doc.flags.no_welcome_mail = True

	if first_name or doc.is_new():
		doc.first_name = first_name or email.split("@")[0]
	doc.last_name = last_name or None
	doc.enabled = int(enabled)
	if role_profiles is not None:
		doc.set("role_profiles", [{"role_profile": name} for name in role_profiles])
	doc.save()
	if not user:
		sign_in.create_link(issuer, subject, doc.name)
	return {"user": doc.name, "enabled": bool(doc.enabled), "linked": True, "user_type": doc.user_type}


def set_enabled(data: dict) -> dict:
	issuer = _issuer(data)
	subject = _text(data, "subject", MAX_SUBJECT)
	enabled = _bool(data, "enabled")
	doc = frappe.get_doc("User", _linked_user_or_404(issuer, subject))
	if bool(doc.enabled) != enabled:
		doc.enabled = int(enabled)
		doc.save()
	return {"user": doc.name, "enabled": bool(doc.enabled)}


def change_email(data: dict) -> dict:
	issuer = _issuer(data)
	subject = _text(data, "subject", MAX_SUBJECT)
	new_email = _email(data.get("new_email"))
	user = _linked_user_or_404(issuer, subject)
	if user == new_email:
		return {"user": user}
	if frappe.db.exists("User", new_email):
		frappe.throw(
			_("The new e-mail address belongs to another user.", context="platform_core.kimlik"), EmailInUse
		)
	rename_doc("User", user, new_email, show_alert=False)
	return {"user": new_email}


def _linked_user(issuer: str, subject: str) -> str | None:
	return frappe.db.get_value(LINK, {"issuer": issuer, "subject": subject}, "user")


def _linked_user_or_404(issuer: str, subject: str) -> str:
	user = _linked_user(issuer, subject)
	if not user:
		frappe.throw(
			_("No user is linked to this identity.", context="platform_core.kimlik"), IdentityNotFound
		)
	return user


def _issuer(data: dict) -> str:
	issuer = _text(data, "issuer", MAX_ISSUER)
	if issuer != site_settings.issuer():
		frappe.throw(
			_("Issuer is not the configured identity provider.", context="platform_core.kimlik"),
			UnknownIssuer,
		)
	return issuer


def _text(data: dict, field: str, max_length: int | None = None) -> str:
	value = data.get(field)
	if not isinstance(value, str) or not value.strip():
		frappe.throw(_("Field {0} is required.", context="platform_core.kimlik").format(field), InvalidInput)
	value = value.strip()
	if max_length and len(value) > max_length:
		frappe.throw(
			_("Field {0} is longer than {1} characters.", context="platform_core.kimlik").format(
				field, max_length
			),
			InvalidInput,
		)
	return value


def _optional_text(data: dict, field: str) -> str:
	value = data.get(field)
	if value is None:
		return ""
	if not isinstance(value, str):
		frappe.throw(_("Field {0} must be text.", context="platform_core.kimlik").format(field), InvalidInput)
	return value.strip()


def _email(value: object) -> str:
	if not isinstance(value, str) or not value.strip():
		frappe.throw(
			_("Field {0} is required.", context="platform_core.kimlik").format("email"), InvalidInput
		)
	email = value.strip().lower()
	if validate_email_address(email) != email:
		frappe.throw(_("E-mail address is not valid.", context="platform_core.kimlik"), InvalidInput)
	return email


def _bool(data: dict, field: str, default: bool | None = None) -> bool:
	value = data.get(field, default)
	if isinstance(value, bool):
		return value
	if isinstance(value, int) and value in (0, 1):
		return bool(value)
	if isinstance(value, str) and value.strip().lower() in ("true", "false", "1", "0"):
		return value.strip().lower() in ("true", "1")
	frappe.throw(
		_("Field {0} must be true or false.", context="platform_core.kimlik").format(field), InvalidInput
	)


def _role_profiles(value: object) -> list[str] | None:
	if value is None:
		return None
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.strip().startswith("[") else [value]
	if not isinstance(value, list) or not all(isinstance(name, str) and name.strip() for name in value):
		frappe.throw(
			_("Field {0} must be a list of role profile names.", context="platform_core.kimlik").format(
				"role_profiles"
			),
			InvalidInput,
		)
	names = sorted({name.strip() for name in value})
	for name in names:
		if not frappe.db.exists("Role Profile", name):
			frappe.throw(
				_("Role profile {0} does not exist.", context="platform_core.kimlik").format(name),
				InvalidInput,
			)
	_no_desk_role(names)
	return names


def _no_desk_role(profiles: list[str]) -> None:
	"""G-16: an end user never gets a role with `desk_access`. `get_all` is used because this is a system check (G-3)."""
	if not profiles:
		return
	roles = frappe.get_all(
		"Has Role",
		filters={"parenttype": "Role Profile", "parent": ("in", profiles)},
		pluck="role",
		limit=500,
	)
	if not roles:
		return
	desk_roles = frappe.get_all(
		"Role", filters={"name": ("in", roles), "desk_access": 1}, pluck="name", limit=1
	)
	if desk_roles:
		frappe.throw(
			_("Role profile grants desk access: {0}", context="platform_core.kimlik").format(desk_roles[0]),
			DeskRoleNotAllowed,
		)
