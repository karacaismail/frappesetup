"""G-62: the “Tenant Admin” role manages the roles and permissions of its own site.

The role has no desk access, so its holders stay Website Users like every panel user.
A tenant is its own Frappe site: the role, the session and every record live on that site only.

The holder can neither give nor change the “System Manager” and “Administrator” roles.
The guards below run for every caller without one of those two roles, not only for this role.
The holder also cannot add permission rows to the role and permission types themselves.
Otherwise the holder could widen its own power step by step.

Frappe reads the permissions of “Custom DocPerm” only from its own definition, so a role
cannot get a stored permission row on it. The holder changes permission rows through the
three permission row functions at the end of this file instead.

Known limit: an Access Rule on a type governs the whole type (decision note 0006).
A System Manager without a rule on that type then loses role access to its records.
The engine warns about such roles when the rule is saved.
"""

import frappe
from frappe import _
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.permissions import (
	add_permission,
	rights,
	setup_custom_perms,
	update_permission_property,
)

from platform_core.access import rules

ROLE = "Tenant Admin"
PROTECTED_ROLES = frozenset({"Administrator", "System Manager"})

_FULL = ("read", "write", "create", "delete", "report", "export")
# The level 0 permissions the role gets. “User” is read only: the panel's explanation form
# asks about user records, and a user permission points to a user.
GRANTS = {
	"Role": _FULL,
	"Role Profile": _FULL,
	"User Permission": _FULL,
	rules.RULE_DOCTYPE: _FULL,
	"User": ("read", "report"),
}
# Higher level permissions. The role list of a profile is at level 1.
LEVEL_GRANTS = {("Role Profile", 1): ("read", "write")}
# Permission rows of these types are written by a System Manager only.
CLOSED_PERMISSION_TYPES = rules.PROTECTED_DOCTYPES | {"User"}


def ensure_role() -> None:
	"""Creates the role and its permission rows. Runs after install and after every migrate."""
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc(doctype="Role", role_name=ROLE, desk_access=0).insert(ignore_permissions=True)
	grants = {(doctype, 0): ptypes for doctype, ptypes in GRANTS.items()} | LEVEL_GRANTS
	for (doctype, level), ptypes in grants.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		# The standard rows are copied first, so the other roles keep their permission.
		setup_custom_perms(doctype)
		row = {"parent": doctype, "role": ROLE, "permlevel": level, "if_owner": 0}
		if not frappe.db.exists("Custom DocPerm", row):
			add_permission(doctype, ROLE, level, ptypes[0])
		for ptype in ptypes:
			if not frappe.db.get_value("Custom DocPerm", row, ptype):
				update_permission_property(doctype, ROLE, level, ptype, 1, validate=False)
	frappe.clear_cache()


# --- guards ---


def _trusted() -> bool:
	"""Installation, migration and the two protected roles are not limited."""
	flags = frappe.flags
	# The copy of the standard rows below is the framework's own step, not the caller's change.
	if flags.platform_copying_perms:
		return True
	if flags.in_install or flags.in_migrate or flags.in_patch or flags.in_setup_wizard:
		return True
	user = frappe.session.user
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def _deny(message: str) -> None:
	frappe.throw(message, frappe.PermissionError, title=_("Not permitted"))


def _protected_message() -> str:
	return _("Only a System Manager can give or change the System Manager and Administrator roles.")


def _before(doc):
	"""The stored version of the record, or `None` for a new record."""
	if doc.is_new():
		return None
	return doc.get_doc_before_save() or frappe.get_doc(doc.doctype, doc.name)


def _child_roles(doc) -> set[str]:
	return {row.role for row in doc.get("roles") or []}


def guard_role(doc, method=None, *args, **kwargs) -> None:
	"""A protected role is not changed, renamed or deleted. A role does not get desk access."""
	if _trusted():
		return
	# `before_rename` passes the old and the new name.
	names = {doc.name, doc.get("role_name"), *(arg for arg in args if isinstance(arg, str))}
	if names & PROTECTED_ROLES:
		_deny(_protected_message())
	if method == "validate" and doc.desk_access:
		before = _before(doc)
		if before is None or not before.desk_access:
			_deny(_("Only a System Manager can give a role desk access."))


def guard_role_profile(doc, method=None, *args, **kwargs) -> None:
	"""A profile that holds a protected role, before or after the change, is left alone."""
	if _trusted():
		return
	roles = _child_roles(doc)
	before = _before(doc)
	if before is not None:
		roles |= _child_roles(before)
	if roles & PROTECTED_ROLES:
		_deny(_protected_message())


def guard_custom_docperm(doc, method=None, *args, **kwargs) -> None:
	"""Rows of a protected role and rows of the permission types are left alone."""
	if _trusted():
		return
	before = _before(doc)
	for row in (doc, before):
		if row is None:
			continue
		if row.role in PROTECTED_ROLES:
			_deny(_protected_message())
		if row.parent in CLOSED_PERMISSION_TYPES:
			_deny(_("Only a System Manager can change the permissions of {0}.").format(row.parent))
	if method == "before_insert" and doc.parent:
		copy_standard_rows(doc.parent)


def copy_standard_rows(doctype: str) -> None:
	"""The first stored row replaces the standard rows of the type. Copy them first,
	so the other roles keep their permission, as the role permission page does."""
	if frappe.flags.platform_copying_perms:
		return
	frappe.flags.platform_copying_perms = True
	try:
		setup_custom_perms(doctype)
	finally:
		frappe.flags.platform_copying_perms = False


def guard_user_permission(doc, method=None, *args, **kwargs) -> None:
	"""The records of a System Manager or the Administrator are not narrowed."""
	if _trusted():
		return
	users = {doc.user}
	before = _before(doc)
	if before is not None:
		users.add(before.user)
	for user in users:
		if user == "Administrator" or set(frappe.get_roles(user)) & PROTECTED_ROLES:
			_deny(_protected_message())


def guard_access_rule(doc, method=None, *args, **kwargs) -> None:
	"""An access rule of a protected role is not written, changed or deleted."""
	if _trusted():
		return
	before = _before(doc)
	if doc.role in PROTECTED_ROLES or (before is not None and before.role in PROTECTED_ROLES):
		_deny(_protected_message())


def guard_user(doc, method=None, *args, **kwargs) -> None:
	"""A protected role is not added to or removed from a user."""
	if _trusted():
		return
	before = _before(doc)
	old = _child_roles(before) if before is not None else set()
	if (old ^ _child_roles(doc)) & PROTECTED_ROLES:
		_deny(_protected_message())
	if before is not None and doc.name == "Administrator":
		_deny(_protected_message())


# --- permission rows (G-62) ---

ROW_KEYS = ("role", "permlevel", "if_owner")


def require_manager() -> None:
	"""A System Manager or a “Tenant Admin” manages permission rows. Nobody else does."""
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles & {"System Manager", ROLE}:
		frappe.throw(_("No permission to manage role permissions."), frappe.PermissionError)


def _require_type(doctype: str) -> None:
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Document type {0} not found.").format(doctype), frappe.DoesNotExistError)
	if frappe.get_meta(doctype).istable:
		frappe.throw(_("Child tables take the permissions of their parent type."))


def _row_values(row) -> dict:
	values = {key: row.get(key) for key in ROW_KEYS}
	values.update({right: int(row.get(right) or 0) for right in rights})
	values["if_owner"] = int(values["if_owner"] or 0)
	return values


def list_role_permissions(doctype: str) -> dict:
	"""The permission rows of a type. Stored rows win over the standard rows of the type."""
	require_manager()
	_require_type(doctype)
	stored = frappe.db.exists("Custom DocPerm", {"parent": doctype})
	# The permission rows are system data of the type (exception to G-3).
	rows = frappe.get_all(
		"Custom DocPerm" if stored else "DocPerm",
		filters={"parent": doctype},
		fields=[*ROW_KEYS, *rights],
		order_by="permlevel asc, role asc, if_owner asc",
		limit=0,
	)
	return {"doctype": doctype, "stored": bool(stored), "rows": [_row_values(row) for row in rows]}


def _key(doctype: str, role: str, permlevel, if_owner) -> dict:
	try:
		permlevel, if_owner = int(permlevel), int(if_owner)
	except (TypeError, ValueError):
		frappe.throw(_("permlevel and if_owner must be whole numbers."))
	if not 0 <= permlevel <= 9 or if_owner not in (0, 1):
		frappe.throw(_("permlevel must be from 0 to 9 and if_owner must be 0 or 1."))
	if not role or not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} not found.").format(role), frappe.DoesNotExistError)
	return {"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": if_owner}


def set_role_permission(doctype: str, role: str, permissions: dict, permlevel=0, if_owner=0) -> dict:
	"""Creates or changes the stored permission row of a role. The guards above still run."""
	require_manager()
	_require_type(doctype)
	key = _key(doctype, role, permlevel, if_owner)
	if not isinstance(permissions, dict) or not permissions or set(permissions) - set(rights):
		frappe.throw(_("permissions must name only these rights: {0}").format(", ".join(rights)))
	values = {right: 1 if permissions[right] else 0 for right in permissions}
	copy_standard_rows(doctype)
	name = frappe.db.get_value("Custom DocPerm", key)
	doc = frappe.get_doc("Custom DocPerm", name) if name else frappe.new_doc("Custom DocPerm")
	doc.update({**key, **values})
	# The caller's right was checked above. The guards of this module run on save.
	if name:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	validate_permissions_for_doctype(doctype)
	frappe.clear_cache(doctype=doctype)
	return {"doctype": doctype, **_row_values(frappe.get_doc("Custom DocPerm", doc.name))}


def remove_role_permission(doctype: str, role: str, permlevel=0, if_owner=0) -> dict:
	"""Deletes the stored permission row of a role. The guards above still run."""
	require_manager()
	_require_type(doctype)
	key = _key(doctype, role, permlevel, if_owner)
	copy_standard_rows(doctype)
	name = frappe.db.get_value("Custom DocPerm", key)
	if not name:
		frappe.throw(_("The role has no permission row at this level."), frappe.DoesNotExistError)
	frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
	validate_permissions_for_doctype(doctype, for_remove=True)
	frappe.clear_cache(doctype=doctype)
	return {"doctype": doctype, "role": role, "permlevel": key["permlevel"], "if_owner": key["if_owner"]}
