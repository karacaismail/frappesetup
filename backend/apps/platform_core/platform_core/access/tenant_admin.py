"""G-62: the “Tenant Admin” role manages the roles and permissions of its own site.

The role has no desk access, so its holders stay Website Users like every panel user.
A tenant is its own Frappe site: the role, the session and every record live on that site only.

The holder can neither give nor change the “System Manager” and “Administrator” roles.
The guards below run for every caller without one of those two roles, not only for this role.
The holder gives permission rows only on business types (`grantable_type`). Framework and
platform types stay closed: a script, sign-in, token or settings type would carry the holder
to System Manager power. The holder gives only plain roles (`grantable_role`): a desk role or
“Script Manager” would make its users System Users and lift the panel's method list.

Frappe reads the permissions of “Custom DocPerm” only from its own definition, so a role
cannot get a stored permission row on it. The holder changes permission rows through the
three permission row functions at the end of this file instead.

Known limit: an Access Rule on a type governs the whole type (decision note 0006).
A System Manager without a rule on that type then loses role access to its records.
The engine warns about such roles when the rule is saved.
"""

import frappe
from frappe import _
from frappe.core.doctype.custom_docperm.custom_docperm import update_custom_docperm
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.core.doctype.role.role import STANDARD_ROLES
from frappe.modules.utils import get_module_app
from frappe.permissions import add_permission, rights, setup_custom_perms
from frappe.utils import cint

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
# Types of these applications hold scripts, sign-in, tokens, settings and the platform's own
# records. Their permission rows are written by a System Manager only.
CLOSED_APPS = frozenset({"frappe", "platform_core"})
# Only the platform operator gives a reseller role (G-169).
RESELLER_ROLES = frozenset({"Reseller Admin", "Reseller Assistant"})
# The holder cannot change these roles, give them to anyone or give them permission rows.
CLOSED_ROLES = frozenset(STANDARD_ROLES) | {ROLE} | RESELLER_ROLES


def ensure_permissions() -> None:
	"""Gives the role its permission rows. Runs after the setup step. Without the role it does nothing."""
	if not frappe.db.exists("Role", ROLE):
		return
	grants = {(doctype, 0): ptypes for doctype, ptypes in GRANTS.items()} | LEVEL_GRANTS
	for (doctype, level), ptypes in grants.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		# The standard rows are copied first, so the other roles keep their permission.
		setup_custom_perms(doctype)
		row = {"parent": doctype, "role": ROLE, "permlevel": level, "if_owner": 0}
		if not frappe.db.exists("Custom DocPerm", row):
			add_permission(doctype, ROLE, level, ptypes[0])
		# Installation reads its own permission row (exception to G-3).
		name = frappe.db.get_value("Custom DocPerm", row)
		missing = {ptype: 1 for ptype in ptypes if not frappe.db.get_value("Custom DocPerm", name, ptype)}
		if missing:
			# The row without “if owner” gets the rights. Each migrate gives back a removed right.
			update_custom_docperm(name, missing)
	frappe.clear_cache()


def _has_password(meta) -> bool:
	"""A password field of the type or of one of its child tables."""
	for field in meta.fields:
		if field.fieldtype == "Password":
			return True
		if field.fieldtype in frappe.model.table_fields and field.options:
			if any(child.fieldtype == "Password" for child in frappe.get_meta(field.options).fields):
				return True
	return False


def grantable_type(doctype: str) -> bool:
	"""A business type: not single, without a password field and outside the closed applications.

	A type a System Manager made on the site (`custom`) belongs to no application and is open.
	Any other type belongs to the application of its module. The dock placement of a module
	(`Module Def.app_name`) is not used: it only says where a custom module is shown.
	"""
	if not doctype or not frappe.db.exists("DocType", doctype):
		return False
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle or _has_password(meta):
		return False
	if meta.custom:
		return True
	try:
		app = get_module_app(meta.module)
	except frappe.DoesNotExistError:
		return False
	return app not in CLOSED_APPS


def grantable_role(role: str) -> bool:
	"""A plain role: not a standard role, not this role and without desk access."""
	if not role or role in CLOSED_ROLES:
		return False
	# The role list is system data (exception to G-3).
	return not frappe.db.get_value("Role", role, "desk_access")


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


def _role_message(role: str) -> str:
	return _("Only a System Manager can give or change the role {0}.").format(role)


def _before(doc):
	"""The stored version of the record, or `None` for a new record."""
	if doc.is_new():
		return None
	return doc.get_doc_before_save() or frappe.get_doc(doc.doctype, doc.name)


def _child_roles(doc) -> set[str]:
	return {row.role for row in doc.get("roles") or []}


def guard_role(doc, method=None, *args, **kwargs) -> None:
	"""Only a plain role is made, changed, renamed or deleted. A role does not get desk access.

	A desk role is not plain. Turning its desk access or 2FA off, or disabling it, would hit
	every user of the role, a System Manager too.
	"""
	if _trusted():
		return
	# `before_rename` passes the old and the new name.
	names = {doc.name, doc.get("role_name"), *(arg for arg in args if isinstance(arg, str))}
	if names & PROTECTED_ROLES:
		_deny(_protected_message())
	for name in sorted(names & CLOSED_ROLES):
		_deny(_role_message(name))
	before = _before(doc)
	if before is not None and before.desk_access:
		_deny(_role_message(before.name))
	if method == "before_validate" and doc.desk_access:
		_deny(_("Only a System Manager can give a role desk access."))


def guard_role_profile(doc, method=None, *args, **kwargs) -> None:
	"""A profile holds only plain roles. A profile that held another role is left alone."""
	if _trusted():
		return
	roles = _child_roles(doc)
	before = _before(doc)
	if before is not None:
		roles |= _child_roles(before)
	if roles & PROTECTED_ROLES:
		_deny(_protected_message())
	for role in sorted(roles):
		if not grantable_role(role):
			_deny(_role_message(role))


def guard_custom_docperm(doc, method=None, *args, **kwargs) -> None:
	"""Only rows of a business type for a role outside the standard roles change."""
	if _trusted():
		return
	before = _before(doc)
	for row in (doc, before):
		if row is None:
			continue
		if row.role in PROTECTED_ROLES:
			_deny(_protected_message())
		if row.role in CLOSED_ROLES:
			_deny(_role_message(row.role))
		if not grantable_type(row.parent):
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
	"""A protected role is not added or removed. Only a plain role is added to a user."""
	if _trusted():
		return
	before = _before(doc)
	old = _child_roles(before) if before is not None else set()
	new = _child_roles(doc)
	if (old ^ new) & PROTECTED_ROLES:
		_deny(_protected_message())
	for role in sorted(new - old):
		if not grantable_role(role):
			_deny(_role_message(role))
	for role in sorted((old - new) & CLOSED_ROLES):
		_deny(_role_message(role))
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
	if not _trusted() and not grantable_type(doctype):
		_deny(_("Only a System Manager can change the permissions of {0}.").format(doctype))
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


def _require_open(doctype: str, role: str) -> None:
	"""The guards below run on save too. This check comes before the copy of the standard rows."""
	if _trusted():
		return
	if role in PROTECTED_ROLES:
		_deny(_protected_message())
	if role in CLOSED_ROLES:
		_deny(_role_message(role))
	if not grantable_type(doctype):
		_deny(_("Only a System Manager can change the permissions of {0}.").format(doctype))


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
	_require_open(doctype, role)
	if not isinstance(permissions, dict) or not permissions or set(permissions) - set(rights):
		frappe.throw(_("permissions must name only these rights: {0}").format(", ".join(rights)))
	# JSON gives true and false. A form gives the text "0" or "1".
	values = {
		right: int(given) if isinstance(given, bool) else 1 if cint(given) else 0
		for right, given in permissions.items()
	}
	copy_standard_rows(doctype)
	# The caller's right was checked by `require_manager` (exception to G-3).
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
	_require_open(doctype, role)
	copy_standard_rows(doctype)
	# The caller's right was checked by `require_manager` (exception to G-3).
	name = frappe.db.get_value("Custom DocPerm", key)
	if not name:
		frappe.throw(_("The role has no permission row at this level."), frappe.DoesNotExistError)
	frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
	validate_permissions_for_doctype(doctype, for_remove=True)
	frappe.clear_cache(doctype=doctype)
	return {"doctype": doctype, "role": role, "permlevel": key["permlevel"], "if_owner": key["if_owner"]}


class GuardedRoleProfile:
	"""Extends “Role Profile” (`extend_doctype_class`): the profile change reaches its users.

	Frappe saves each user of the profile as the session user. A “Tenant Admin” has no write
	permission on users, so the save would fail. The user's roles change only through the
	profile, so the save skips the permission check. `guard_user` still runs on each save.
	A user who holds a role that is not plain is skipped: the sync would take that role away.
	"""

	def update_all_users(self):
		if _trusted():
			return super().update_all_users()
		# The profile's own users, read for the sync (exception to G-3). A profile is small.
		users = frappe.get_all(
			"User Role Profile", filters={"role_profile": self.name}, pluck="parent", limit=0
		)
		skipped = []
		for name in users:
			user = frappe.get_doc("User", name)
			# The sync drops every role outside the profile. A role that is not plain stays.
			if name == "Administrator" or any(not grantable_role(row.role) for row in user.roles):
				skipped.append(name)
				continue
			user.flags.ignore_permissions = True
			user.save()
		if skipped:
			frappe.logger("platform_core.access").info(
				"Role Profile %s: %s users kept their roles; a System Manager saves them.",
				self.name,
				len(skipped),
			)
