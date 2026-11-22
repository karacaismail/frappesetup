"""Anonymize account data without changing invoices or unrelated accounts."""

import logging
from email.utils import formataddr, getaddresses
from hashlib import sha256
from time import monotonic

import frappe
from frappe.model.rename_doc import get_link_fields, rename_parent_and_child
from frappe.utils.password import remove_encrypted_password

from press_tr.kimlik.identity import DELETED_IDENTITY_ISSUER, deleted_identity_subject, find_identity
from press_tr.kimlik.oidc import reject

PROFILE_FIELDS = (
	"gender",
	"last_ip",
	"reset_password_key",
	"short_bio",
)
EXTERNAL_EMAIL_FIELDS = {("Communication", "recipients"), ("Email Unsubscribe", "email")}
PRIVATE_CHILDREN = ("User Social Login", "User Email")


def anonymize_linked_user(issuer: str, subject: str) -> bool:
	started = monotonic()
	digest = deleted_identity_subject(issuer, subject)
	link = find_identity(issuer, subject, for_update=True)
	if not link:
		link = find_identity(DELETED_IDENTITY_ISSUER, digest, for_update=True)
	if not link:
		return False

	user = link.user
	if user in {"Guest", "Administrator", frappe.conf.press_identity_sync_user}:
		reject()
	profile = frappe.db.get_value(
		"User", user, ["name", "user_type", "email", "user_image"], as_dict=True, for_update=True
	)
	if not profile or profile.user_type != "Website User":
		reject()

	placeholder = f"deleted-{sha256(link.name.encode()).hexdigest()[:32]}@invalid.example"
	if user == placeholder and link.issuer == DELETED_IDENTITY_ISSUER:
		return True

	close_account(link.name, user)
	frappe.db.set_value(
		"Press Identity Link", link.name, {"issuer": DELETED_IDENTITY_ISSUER, "subject": digest}
	)
	# The deletion contract makes revocation durable before profile redaction.
	frappe.db.commit()
	link = find_identity(DELETED_IDENTITY_ISSUER, digest, for_update=True)
	if link.user != placeholder:
		redact_profile(profile, placeholder)
	frappe.logger("press_tr").log(
		logging.INFO, "Account anonymization finished in %.3f seconds", monotonic() - started
	)
	return True


def close_account(identity_link: str, user: str) -> None:
	frappe.db.set_value("User", user, {"enabled": 0, "api_key": None})
	remove_encrypted_password("User", user, "api_secret")
	remove_encrypted_password("User", user)
	table = frappe.qb.DocType("Sessions")
	while sessions := (
		frappe.qb.from_(table)
		.select(table.sid)
		.where(table.user == user)
		.orderby(table.sid)
		.limit(100)
		.run(pluck=True)
	):
		frappe.db.delete("Sessions", {"sid": ["in", sessions]})
		frappe.db.after_commit.add(lambda sids=tuple(sessions): clear_session_cache(user, sids))
	frappe.db.after_commit.add(lambda: clear_session_cache(user, ()))
	for name in frappe.get_all(
		"Press Keycloak Session", filters={"identity_link": identity_link}, pluck="name"
	):
		remove_encrypted_password("Press Keycloak Session", name, "press_sid")
	frappe.db.delete("Press Keycloak Session", {"identity_link": identity_link})


def redact_profile(profile, placeholder: str) -> None:
	user = profile.name
	email = profile.email
	fields_by_type = {}
	for spec in frappe.get_hooks("user_data_fields"):
		doctype = spec["doctype"]
		if doctype == "Invoice" or not frappe.db.exists("DocType", doctype):
			continue
		fields_by_type.setdefault(doctype, set()).update(spec.get("redact_fields", ()))
		field = spec.get("filter_by")
		if doctype in {"User", "Contact", "Contact Email", "File", "Address"}:
			continue
		if spec.get("strict") and not field:
			if doctype == "Access Log":
				frappe.db.set_value(doctype, {"user": user}, "user", placeholder, update_modified=False)
			elif doctype == "Comment":
				frappe.db.set_value(
					doctype,
					{"comment_email": email},
					{
						"comment_email": placeholder,
						"comment_by": "Deleted",
					},
					update_modified=False,
				)
			continue
		if not field:
			continue
		# The framework hooks also mark some values as partial. Scope matching
		# to the address itself so similarly named accounts remain untouched.
		values = {
			field: placeholder
			if field in {"sender", "recipient", "recipients", "email", "email_id"}
			else None
		}
		values.update(dict.fromkeys(spec.get("redact_fields", ())))
		frappe.db.set_value(doctype, {field: email}, values, update_modified=False)
		if (doctype, field) in EXTERNAL_EMAIL_FIELDS:
			redact_address_lists(doctype, field, email, placeholder)

	redact_user_contacts(
		user, email, placeholder, fields_by_type.get("Contact", set()), fields_by_type.get("Address", set())
	)
	profile_fields = fields_by_type.get("User", set()) | set(PROFILE_FIELDS)
	frappe.db.set_value(
		"User",
		user,
		dict.fromkeys(profile_fields & set(frappe.db.get_table_columns("User")))
		| {"email": placeholder, "first_name": "Deleted", "full_name": "Deleted"},
	)
	for doctype in PRIVATE_CHILDREN:
		if frappe.db.exists("DocType", doctype):
			frappe.db.delete(doctype, {"parent": user, "parenttype": "User"})
	frappe.db.delete("DefaultValue", {"parent": user})
	frappe.db.delete("Notification Settings", {"name": user})
	for field in ("totp_secret", "otp_secret"):
		remove_encrypted_password("User", user, field)
	if frappe.db.exists("DocType", "User 2FA"):
		for name in frappe.get_all("User 2FA", filters={"user": user}, pluck="name"):
			remove_encrypted_password("User 2FA", name, "totp_secret")
			frappe.db.delete("User 2FA", {"name": name})

	frappe.db.set_value(
		"Activity Log",
		{"user": user},
		{"full_name": "Deleted", "subject": "Account activity", "ip_address": None},
		update_modified=False,
	)
	frappe.db.delete("Version", {"ref_doctype": "User", "docname": user})

	for name in get_personal_files(user, profile.user_image):
		frappe.delete_doc("File", name, ignore_permissions=True)

	clean_press_ownership(user)
	rename_linked_record("User", user, placeholder)
	frappe.db.after_commit.add(lambda: clear_session_cache(user, ()))


def get_personal_files(user: str, image: str | None) -> set[str]:
	queries = [
		{"attached_to_doctype": "User", "attached_to_name": user},
		{"owner": user, "is_private": 1, "attached_to_doctype": ["is", "not set"]},
	]
	if image:
		queries.append({"owner": user, "file_url": image, "attached_to_doctype": ["is", "not set"]})
	# Frappe flattens or_filters into individual OR terms. Each scope needs AND.
	return {
		name
		for filters in queries
		for name in frappe.get_all("File", {"is_folder": 0, **filters}, pluck="name")
	}


def redact_address_lists(doctype: str, field: str, email: str, placeholder: str) -> None:
	for row in frappe.get_all(doctype, {field: ["like", f"%{email}%"]}, ["name", field]):
		addresses = getaddresses([row[field]])
		if any(address.lower() == email.lower() for _, address in addresses):
			replaced = [
				placeholder if address.lower() == email.lower() else formataddr((name, address))
				for name, address in addresses
			]
			frappe.db.set_value(doctype, row.name, field, ", ".join(replaced), update_modified=False)


def redact_user_contacts(
	user: str, email: str, placeholder: str, fields: set[str], address_fields: set[str]
) -> None:
	contacts = set(frappe.get_all("Contact", or_filters={"user": user, "email_id": email}, pluck="name"))
	contacts.update(
		frappe.get_all("Contact Email", {"email_id": email, "parenttype": "Contact"}, pluck="parent")
	)
	addresses = set(frappe.get_all("Address", {"email_id": email}, pluck="name"))
	for link_doctype, names in (("User", [user]), ("Contact", contacts)):
		if names:
			addresses.update(
				frappe.get_all(
					"Dynamic Link",
					{"parenttype": "Address", "link_doctype": link_doctype, "link_name": ["in", list(names)]},
					pluck="parent",
				)
			)
	for address in sorted(addresses):
		frappe.db.set_value(
			"Address",
			address,
			dict.fromkeys(address_fields | {"email_id", "country"}) | {"address_title": "Deleted"},
			update_modified=False,
		)
		frappe.db.delete("Version", {"ref_doctype": "Address", "docname": address})
		suffix = sha256(f"{placeholder}:{address}".encode()).hexdigest()[:32]
		rename_linked_record("Address", address, f"deleted-{suffix}")

	for contact in sorted(contacts):
		for child_type in ("Contact Email", "Contact Phone"):
			frappe.db.delete(child_type, {"parent": contact, "parenttype": "Contact"})
		frappe.db.set_value(
			"Contact",
			contact,
			dict.fromkeys(
				(fields | {"middle_name", "email_id", "gender", "image", "google_contacts_id", "salutation"})
				& set(frappe.db.get_table_columns("Contact"))
			)
			| {"first_name": "Deleted", "full_name": "Deleted"},
		)
		frappe.db.delete("Version", {"ref_doctype": "Contact", "docname": contact})
		suffix = sha256(f"{placeholder}:{contact}".encode()).hexdigest()[:32]
		rename_linked_record("Contact", contact, f"deleted-{suffix}")


def clean_press_ownership(user: str) -> None:
	for doctype in ("SSH Certificate", "User SSH Certificate"):
		if frappe.db.exists("DocType", doctype):
			fields = set(frappe.db.get_table_columns(doctype))
			certificate_fields = {
				"ssh_certificate",
				"ssh_public_key",
				"certificate_details",
				"ssh_command",
				"user_ssh_key",
			}
			frappe.db.set_value(
				doctype,
				{"user": user},
				dict.fromkeys(certificate_fields & fields) | {"valid_until": frappe.utils.now_datetime()},
				update_modified=False,
			)
	if frappe.db.exists("DocType", "User SSH Key"):
		for name in frappe.get_all("User SSH Key", {"user": user}, pluck="name"):
			frappe.delete_doc("User SSH Key", name, ignore_permissions=True)

	teams = set(frappe.get_all("Team Member", {"user": user, "parenttype": "Team"}, pluck="parent"))
	teams.update(frappe.get_all("Team", {"user": user}, pluck="name"))
	for team in sorted(teams):
		owner = frappe.db.get_value("Team", team, "user", for_update=True)
		members = frappe.get_all("Team Member", {"parenttype": "Team", "parent": team}, pluck="user")
		if owner == user:
			frappe.db.set_value("Team", team, {"billing_name": None, "phone_number": None})
			for version in frappe.get_all(
				"Version", {"ref_doctype": "Team", "docname": team}, ["name", "data"]
			):
				data = frappe.parse_json(version.data)
				changes = data.get("changed", [])
				cleaned = [change for change in changes if change[0] not in {"billing_name", "phone_number"}]
				if cleaned != changes:
					data["changed"] = cleaned
					frappe.db.set_value(
						"Version", version.name, "data", frappe.as_json(data), update_modified=False
					)

		if set(members) == {user} or (not members and owner == user):
			frappe.db.set_value("Team", team, "enabled", 0)
			for name in frappe.get_all(
				"Site", {"team": team, "status": ["not in", ["Archived", "Suspended"]]}, pluck="name"
			):
				site = frappe.get_doc("Site", name, for_update=True)
				site.suspend(reason="Account anonymized")
				site.save(ignore_permissions=True)


def rename_linked_record(doctype: str, old: str, new: str) -> None:
	# Use the exact link fields from Frappe metadata, without global owner scans,
	# rename hooks, edit comments or realtime events. Invoice is a legal record.
	rename_parent_and_child(doctype, old, new, frappe.get_meta(doctype))
	for link in get_link_fields(doctype):
		table, field = link["parent"], link["fieldname"]
		if table == "Invoice":
			continue
		if link["issingle"]:
			if frappe.db.get_single_value(table, field) == old:
				frappe.db.set_single_value(table, field, new)
		else:
			replace_link_by_primary_key(table, {field: old}, field, new)
	replace_link_by_primary_key(
		"Dynamic Link",
		{"link_doctype": doctype, "link_name": old, "parenttype": ["!=", "Invoice"]},
		"link_name",
		new,
	)


def replace_link_by_primary_key(doctype: str, filters: dict, field: str, value: str) -> None:
	# Read matching names first. UPDATE must not lock unrelated rows in a table
	# whose link field has no index.
	while names := frappe.get_all(doctype, filters, pluck="name", order_by="name asc", limit=100):
		frappe.db.set_value(doctype, {**filters, "name": ["in", names]}, field, value, update_modified=False)
		if len(names) < 100:
			break
		filters = {**filters, "name": [">", names[-1]]}


def clear_session_cache(user: str, sessions: tuple[str, ...]) -> None:
	frappe.clear_cache(user=user)
	for sid in sessions:
		frappe.cache.hdel("session", sid)
	frappe.cache.delete_key("users_for_mentions")
	frappe.cache.delete_key("enabled_users")
