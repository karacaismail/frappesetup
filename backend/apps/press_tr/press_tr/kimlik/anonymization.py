"""Anonymize Press account profiles while preserving linked business documents."""

from hashlib import sha256

import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc
from frappe.utils.password import remove_encrypted_password

from press_tr.kimlik.identity import find_identity
from press_tr.kimlik.oidc import reject

USER_PROFILE_FIELDS = (
	"middle_name",
	"last_name",
	"username",
	"gender",
	"phone",
	"mobile_no",
	"birth_date",
	"location",
	"user_image",
	"banner_image",
	"short_bio",
	"bio",
	"interest",
	"email_signature",
	"last_ip",
	"reset_password_key",
)
CONTACT_PROFILE_FIELDS = (
	"middle_name",
	"last_name",
	"salutation",
	"gender",
	"email_id",
	"phone",
	"mobile_no",
	"image",
	"google_contacts_id",
)


def anonymize_linked_user(issuer: str, subject: str) -> None:
	link = find_identity(issuer, subject, for_update=True)
	if not link:
		return

	user = link.user
	if user in {"Guest", "Administrator", frappe.conf.press_identity_sync_user}:
		reject()

	profile = frappe.db.get_value("User", user, ["name", "user_type"], as_dict=True, for_update=True)
	if not profile or profile.user_type != "Website User":
		reject()

	placeholder = f"deleted-{sha256(link.name.encode()).hexdigest()[:32]}@invalid.example"
	if user == placeholder:
		return

	# User.after_rename normally clears sessions via a Frappe API that commits.
	# Remove the rows in this transaction and invalidate their cache after commit.
	session_table = frappe.qb.DocType("Sessions")
	sessions = (
		frappe.qb.from_(session_table)
		.select(session_table.sid)
		.where(session_table.user == user)
		.run(pluck=True)
	)
	frappe.db.delete("Sessions", {"user": user})
	frappe.db.after_commit.add(lambda: clear_session_cache(user, sessions))
	for name in frappe.get_all("Press Keycloak Session", filters={"identity_link": link.name}, pluck="name"):
		remove_encrypted_password("Press Keycloak Session", name, "press_sid")
	frappe.db.delete("Press Keycloak Session", {"identity_link": link.name})

	frappe.db.set_value(
		"User",
		user,
		dict.fromkeys(set(USER_PROFILE_FIELDS) & set(frappe.db.get_table_columns("User")))
		| {"enabled": 0, "api_key": None, "first_name": "Deleted", "full_name": "Deleted"},
	)
	remove_encrypted_password("User", user, "api_secret")
	remove_encrypted_password("User", user)
	rename_profile("User", user, placeholder)

	for contact in frappe.get_all("Contact", filters={"user": placeholder}, pluck="name"):
		for child_type in ("Contact Email", "Contact Phone"):
			frappe.db.delete(child_type, {"parent": contact, "parenttype": "Contact"})
		frappe.db.set_value(
			"Contact",
			contact,
			dict.fromkeys(set(CONTACT_PROFILE_FIELDS) & set(frappe.db.get_table_columns("Contact")))
			| {"first_name": "Deleted", "full_name": "Deleted"},
		)
		contact_suffix = sha256(f"{link.name}:{contact}".encode()).hexdigest()[:32]
		rename_profile("Contact", contact, f"deleted-{contact_suffix}")


def rename_profile(doctype: str, old: str, new: str) -> None:
	previous_session = frappe.session.copy()
	previous_form = frappe.form_dict.copy()
	try:
		# Press's User rename hook also renames private settings documents.
		frappe.set_user("Administrator")
		rename_doc(
			doctype, old, new, force=True, ignore_permissions=True, show_alert=False, rebuild_search=False
		)
		rename_message = _("renamed from {0} to {1}").format(frappe.bold(old), frappe.bold(new))
	finally:
		frappe.set_user(previous_session["user"])
		frappe.session.update(previous_session)
		frappe.form_dict.update(previous_form)

	# Rename events and comments include the old document name.
	events = getattr(frappe.local, "_realtime_log", [])
	events[:] = [
		entry
		for entry in events
		if not (entry[0] == "doc_rename" and entry[1].get("old") == old and entry[1].get("new") == new)
	]
	frappe.db.set_value(
		"Comment",
		{"reference_name": new, "comment_type": "Edit", "content": rename_message},
		"content",
		_("Account profile anonymized."),
		update_modified=False,
	)


def clear_session_cache(user: str, sessions: list[str]) -> None:
	frappe.clear_cache(user=user)
	for sid in sessions:
		frappe.cache.hdel("session", sid)
	frappe.cache.delete_key("users_for_mentions")
	frappe.cache.delete_key("enabled_users")
