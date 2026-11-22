import frappe
from frappe import _

from press_tr.kimlik.identity import as_press_user, bind_identity, ensure_personal_team, find_identity
from press_tr.kimlik.oidc import claim, reject
from press_tr.kimlik.service import require_service


def lock_team(team: str):
	team = claim({"team": team}, "team")
	try:
		return frappe.get_doc("Team", team, for_update=True)
	except frappe.QueryDeadlockError:
		# This runs before writes. Refresh the snapshot if MariaDB saw a newer team.
		frappe.db.rollback()
		return frappe.get_doc("Team", team, for_update=True)


@frappe.whitelist(methods=["POST"])
def ensure_team(
	issuer: str, subject: str, email: str | None = None, email_verified: bool = False, team: str | None = None
) -> dict[str, str]:
	require_service(issuer)
	try:
		return provision_team(issuer, subject, email, email_verified, team)
	except frappe.DuplicateEntryError, frappe.UniqueValidationError, frappe.QueryDeadlockError:
		# A competing first request may have created the identity and team.
		frappe.db.rollback()
		try:
			return provision_team(issuer, subject, email, email_verified, team)
		except frappe.DuplicateEntryError, frappe.UniqueValidationError:
			reject()


def provision_team(issuer, subject, email, email_verified, team):
	doc = lock_team(team) if team is not None else None
	link = bind_identity({"iss": issuer, "sub": subject, "email": email, "email_verified": email_verified})
	if doc is None:
		team = ensure_personal_team(link.user)
	elif not any(member.user == link.user for member in doc.team_members):
		with as_press_user(doc.user):
			doc.create_user_for_member(email=link.user)
	return {"team": team, "user": link.user}


@frappe.whitelist(methods=["POST"])
def remove_team_member(issuer: str, subject: str, team: str) -> dict[str, str | bool]:
	require_service(issuer)
	link = find_identity(issuer, claim({"subject": subject}, "subject"))
	if not link:
		return {"team": team, "member": False}

	try:
		doc = lock_team(team)
	except frappe.DoesNotExistError:
		return {"team": team, "member": False}
	if doc.user == link.user:
		frappe.throw(_("Change team ownership before removing the owner."), frappe.PermissionError)
	if any(member.user == link.user for member in doc.team_members):
		# Use the team owner so the Press save retains a valid team context.
		with as_press_user(doc.user):
			doc.remove_team_member(link.user)

	return {"team": team, "member": False}
