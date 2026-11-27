import frappe
from frappe import _
from frappe.utils.password import remove_encrypted_password

from press_tr.press_identity.recovery import REVIEWER_ROLE


def revoke_disabled_user_keys(doc, method=None) -> None:
	if not doc.enabled:
		remove_encrypted_password("User", doc.name, "api_secret")
		if doc.api_key:
			doc.db_set("api_key", None, update_modified=False)


def _has_reviewer_role(user) -> bool:
	return user is not None and any(row.role == REVIEWER_ROLE for row in user.roles)


def guard_reviewer_role(doc, method=None) -> None:
	# AJA-421: only Administrator gives or takes the reviewer role. Frappe applies the role
	# profile earlier in User.validate, so this compares the final role list with the stored one.
	if _has_reviewer_role(doc) == _has_reviewer_role(doc.get_doc_before_save()):
		return
	if frappe.session.user != "Administrator":
		frappe.throw(
			_("Only Administrator can give or take the Recovery Reviewer role.", context="press_tr"),
			frappe.PermissionError,
		)


def save_authorized_document(doc) -> None:
	previous = doc.flags.ignore_permissions
	try:
		doc.save(ignore_permissions=True)
	finally:
		doc.flags.ignore_permissions = previous


def disable_user(user: str) -> None:
	# Identity Sync has already authorized this specific linked account.
	doc = frappe.get_doc("User", user, for_update=True)
	if doc.enabled:
		doc.enabled = 0
		save_authorized_document(doc)
	else:
		revoke_disabled_user_keys(doc)


class AccountRequestPolicy:
	def before_insert(self) -> None:
		if self.invited_by:
			frappe.throw(
				_("Press team invitations are disabled.", context="press_tr"), frappe.PermissionError
			)
		super().before_insert()
