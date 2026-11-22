from typing import Any

import frappe
from frappe import _

from press_tr.kimlik.identity import as_press_user, bind_identity, create_team, find_identity
from press_tr.kimlik.oidc import claim, reject
from press_tr.kimlik.service import require_service


def lock_team(organization_id: str):
	# Authentication opens a read snapshot before the Team lock.
	frappe.db.rollback()
	name = frappe.db.get_value("Team", {"keycloak_org_id": organization_id}, "name")
	if not name:
		return None
	# The name lookup uses a snapshot too. Start the write transaction with
	# the parent row lock, before controller code can read a consistent snapshot.
	frappe.db.rollback()
	if not frappe.db.get_value("Team", name, "name", for_update=True):
		return None
	doc = frappe.get_doc("Team", name, for_update=True)
	if doc.keycloak_org_id != organization_id:
		reject()
	return doc


@frappe.whitelist(methods=["POST"])
def ensure_team(
	issuer: str,
	subject: str,
	email: str,
	email_verified: bool,
	organization_id: str,
	organization_name: str | None = None,
) -> dict[str, str | bool]:
	require_service(issuer)
	organization_id = claim({"organization_id": organization_id}, "organization_id")
	title = organization_name if organization_name is not None else organization_id
	title = claim({"organization_name": title}, "organization_name")
	email = claim({"email": email}, "email")
	try:
		return provision_team(issuer, subject, email, email_verified, organization_id, title)
	except frappe.DuplicateEntryError, frappe.UniqueValidationError, frappe.QueryDeadlockError:
		# A competing first request may have created the identity and team.
		frappe.db.rollback()
		try:
			return provision_team(issuer, subject, email, email_verified, organization_id, title)
		except frappe.DuplicateEntryError, frappe.UniqueValidationError:
			reject()


def provision_team(
	issuer: str, subject: str, email: str, email_verified: bool, organization_id: str, title: str
):
	doc = lock_team(organization_id)
	link = bind_identity({"iss": issuer, "sub": subject, "email": email, "email_verified": email_verified})
	if doc is None:
		return {"team": create_team(link.user, title, organization_id), "created": True}
	if not any(member.user == link.user for member in doc.team_members):
		with as_press_user(doc.user):
			doc.create_user_for_member(email=link.user)
	return {"team": doc.name, "created": False}


class InvalidTeamSelector(frappe.ValidationError):
	http_status_code = 400


@frappe.whitelist(methods=["POST"])
def remove_team_member(
	issuer: str, subject: str, organization_id: Any = None, all_organizations: Any = None
) -> dict[str, str | bool | None]:
	require_service(issuer)
	has_organization_id = "organization_id" in frappe.form_dict
	has_all_organizations = "all_organizations" in frappe.form_dict
	if (
		has_organization_id == has_all_organizations
		or (
			has_organization_id
			and (
				not isinstance(organization_id, str)
				or not organization_id.strip()
				or len(organization_id) > 255
			)
		)
		or (has_all_organizations and all_organizations is not True)
	):
		frappe.throw(_("Send exactly one valid organization selector."), InvalidTeamSelector)

	link = find_identity(issuer, claim({"subject": subject}, "subject"))
	if has_all_organizations:
		if link:
			remove_organization_memberships(link.user)
		return {"team": None, "member": False}

	doc = lock_team(organization_id)
	if doc and link:
		remove_memberships([doc], link.user)
	return {"team": doc.name if doc else None, "member": False}


def remove_organization_memberships(user: str) -> None:
	# This authenticated system operation must find all candidate memberships.
	frappe.db.rollback()
	names = frappe.get_all("Team Member", filters={"user": user, "parenttype": "Team"}, pluck="parent")
	if not names:
		return

	# Keep every lock and write in one transaction. Refresh the snapshot before
	# locking, since the membership lookup above used a consistent read.
	frappe.db.rollback()
	names = frappe.db.get_values(
		"Team",
		{"name": ["in", names], "keycloak_org_id": ["is", "set"]},
		"name",
		order_by="name asc",
		for_update=True,
		pluck=True,
	)
	teams = [frappe.get_doc("Team", name, for_update=True) for name in names]
	remove_memberships(teams, user)


def remove_memberships(teams, user: str) -> None:
	# Check owners before the first write so a rejected request has no partial result.
	if any(team.user == user for team in teams):
		frappe.throw(_("Change team ownership before removing the owner."), frappe.PermissionError)
	for team in teams:
		if any(member.user == user for member in team.team_members):
			# Use the team owner so the Press save retains a valid team context.
			with as_press_user(team.user):
				team.remove_team_member(user)
