import hmac
import json
from contextlib import contextmanager
from email.errors import HeaderParseError
from email.headerregistry import Address

import frappe
from frappe import _
from press.press.doctype.team.team import Team
from werkzeug.exceptions import ServiceUnavailable

from press_tr.kimlik.oidc import claim, reject
from press_tr.kimlik.sessions import SESSION_MAPPING_DOCTYPE, read_press_session_id, session_mapping_pages

IDENTITY_LINK = "Press Identity Link"


DELETED_IDENTITY_ISSUER = "urn:press-tr:deleted-identity"


def deleted_identity_subject(issuer: str, subject: str) -> str:
	key = frappe.conf.press_anonymization_hmac_key or frappe.conf.encryption_key
	if not key:
		raise ServiceUnavailable(
			_("Configure a stable site key for Press anonymization.", context="press_tr")
		)
	message = json.dumps([issuer, subject], separators=(",", ":"), ensure_ascii=False).encode()
	return hmac.digest(key.encode(), message, "sha256").hex()


def find_identity(issuer, subject, *, for_update=False):
	link = frappe.db.get_value(
		IDENTITY_LINK,
		{"issuer": issuer, "subject": subject},
		["name", "user", "issuer", "subject"],
		as_dict=True,
		for_update=for_update,
	)
	if link and (link.issuer != issuer or link.subject != subject):
		reject()
	return link


def remember_press_session(identity_link: str, keycloak_sid: str) -> None:
	sid = frappe.session.sid
	for names in session_mapping_pages({"identity_link": identity_link, "keycloak_sid": keycloak_sid}):
		if any(read_press_session_id(name) == sid for name in names):
			return
	frappe.get_doc(
		{
			"doctype": SESSION_MAPPING_DOCTYPE,
			"identity_link": identity_link,
			"keycloak_sid": keycloak_sid,
			"press_sid": sid,
		}
	).insert(ignore_permissions=True)


def bind_identity(claims):
	issuer = claim(claims, "iss")
	subject = claim(claims, "sub")
	link = find_identity(issuer, subject, for_update=True)
	if find_identity(DELETED_IDENTITY_ISSUER, deleted_identity_subject(issuer, subject), for_update=True):
		reject()
	if link:
		validate_local_user(link.user)
		return link

	if claims.get("email_verified") is not True:
		reject()
	email = claim(claims, "email").lower()
	try:
		address = Address(addr_spec=email)
	except ValueError, HeaderParseError:
		reject()
	if len(email) > 140 or address.addr_spec != email:
		reject()

	user = frappe.db.get_value("User", {"email": email}, "name")
	if user:
		# Lock existing users by their primary key, without gap-locking new emails.
		if not frappe.db.get_value("User", user, "name", for_update=True):
			reject()
		validate_local_user(user)
		if frappe.db.exists(IDENTITY_LINK, {"user": user}):
			reject()
	else:
		user = Team.create_user(first_name=email.split("@", 1)[0], email=email).name
		validate_local_user(user)

	link = frappe.get_doc({"doctype": IDENTITY_LINK, "issuer": issuer, "subject": subject, "user": user})
	# Only a verified identity flow can write this internal binding.
	link.insert(ignore_permissions=True)
	return frappe._dict(name=link.name, user=user)


def validate_local_user(user, *, allow_disabled: bool = False):
	if user in {"Administrator", "Guest"}:
		reject()
	enabled, user_type = frappe.db.get_value("User", user, ["enabled", "user_type"]) or (False, None)
	if (
		(not enabled and not allow_disabled)
		or user_type != "Website User"
		or "Press User" not in frappe.get_roles(user)
	):
		reject()


@contextmanager
def as_press_user(user, *, allow_disabled: bool = False):
	validate_local_user(user, allow_disabled=allow_disabled)
	previous_session = frappe.session.copy()
	previous_form = frappe.form_dict.copy()
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous_session["user"])
		frappe.session.update(previous_session)
		frappe.form_dict.update(previous_form)


def ensure_personal_team(user):
	# Lock the owner before checking for an existing personal team.
	frappe.db.get_value("User", user, "name", for_update=True)
	team = frappe.db.get_value("Team Member", {"user": user}, "parent", for_update=True)
	if team:
		return team
	return create_team(user, "Parent Team")


def create_team(user: str, title: str, organization_id: str | None = None) -> str:
	# The Press Team controller creates the team without starting billing.
	doc = frappe.get_doc(
		{
			"doctype": "Team",
			"user": user,
			"team_title": title,
			"keycloak_org_id": organization_id,
			"enabled": 1,
			"team_members": [{"user": user}],
		}
	)
	with as_press_user(user):
		# Only authorized provisioning creates this team and its initial owner.
		doc.insert(ignore_permissions=True)
	return doc.name
