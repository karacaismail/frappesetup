"""G-168: the tenant admin assistant role and its Role Profile.

A tenant admin gives the profile to a member of the same tenant site. The profile replaces the
member's roles with the single assistant role, which has no desk access. So the holder stays a
Website User (G-53) and has neither "Tenant Admin" nor "System Manager".
"""

import frappe
from frappe import _
from frappe.core.doctype.user.user import STANDARD_USERS

ASSISTANT_ROLE = "Tenant Admin Assistant"
ASSISTANT_PROFILE = "Tenant Admin Assistant"
# The role and the profiles are fixtures (`fixtures/role.json`, `fixtures/role_profile.json`).
TENANT_ADMIN_ROLE = "Tenant Admin"
GRANTING_ROLES = frozenset({TENANT_ADMIN_ROLE, "System Manager"})
# A grant replaces all roles, so it must never demote an admin.
PROTECTED_ROLES = frozenset({TENANT_ADMIN_ROLE, "System Manager", "Administrator"})


def grant_assistant(user: str) -> dict:
	"""Gives the assistant Role Profile to a Website User of this site."""
	caller = frappe.session.user
	if not GRANTING_ROLES.intersection(frappe.get_roles(caller)):
		frappe.throw(_("Only a tenant admin can give this role."), frappe.PermissionError)
	if not isinstance(user, str) or not user or user in STANDARD_USERS or user == caller:
		frappe.throw(_("This user cannot receive the role."))
	if not frappe.db.exists("User", user):
		frappe.throw(_("User not found."), frappe.DoesNotExistError)
	doc = frappe.get_doc("User", user)
	if not doc.enabled:
		frappe.throw(_("This user cannot receive the role."))
	if PROTECTED_ROLES.intersection(frappe.get_roles(user)) or doc.user_type != "Website User":
		frappe.throw(_("Only a panel user without admin roles can receive this role."))
	doc.set("role_profiles", [{"role_profile": ASSISTANT_PROFILE}])
	doc.save(ignore_permissions=True)
	return {
		"user": doc.name,
		"role_profile": ASSISTANT_PROFILE,
		"roles": sorted(row.role for row in doc.roles),
	}
