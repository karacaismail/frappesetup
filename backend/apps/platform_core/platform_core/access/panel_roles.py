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
# G-62 defines this role. Until then only a System Manager passes the check in practice.
TENANT_ADMIN_ROLE = "Tenant Admin"
GRANTING_ROLES = frozenset({TENANT_ADMIN_ROLE, "System Manager"})
# A grant replaces all roles, so it must never demote an admin.
PROTECTED_ROLES = frozenset({TENANT_ADMIN_ROLE, "System Manager", "Administrator"})


def ensure_assistant_profile() -> None:
	"""Creates the role and the Role Profile when missing. An unchanged profile is not saved again."""
	if not frappe.db.exists("Role", ASSISTANT_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ASSISTANT_ROLE, "desk_access": 0}).insert(
			ignore_permissions=True
		)
	elif frappe.db.get_value("Role", ASSISTANT_ROLE, "desk_access"):
		frappe.db.set_value("Role", ASSISTANT_ROLE, "desk_access", 0)
	if not frappe.db.exists("Role Profile", ASSISTANT_PROFILE):
		frappe.get_doc(
			{
				"doctype": "Role Profile",
				"role_profile": ASSISTANT_PROFILE,
				"roles": [{"role": ASSISTANT_ROLE}],
			}
		).insert(ignore_permissions=True)
		return
	profile = frappe.get_doc("Role Profile", ASSISTANT_PROFILE)
	if {row.role for row in profile.roles} == {ASSISTANT_ROLE}:
		return
	# A save queues a job and locks the record. Without a worker the lock stays, and the next
	# migrate fails. So the rows are written directly and the holders are synced here.
	frappe.db.delete("Has Role", {"parenttype": "Role Profile", "parent": ASSISTANT_PROFILE})
	profile.set("roles", [])
	profile.append("roles", {"role": ASSISTANT_ROLE}).db_insert()
	profile.clear_cache()
	profile.update_all_users()


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
