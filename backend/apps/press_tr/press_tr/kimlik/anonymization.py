"""Anonymize account data without changing invoices or unrelated accounts."""

import logging
from email.utils import formataddr, getaddresses
from hashlib import sha256
from itertools import batched, groupby
from operator import itemgetter
from time import monotonic

import frappe
from frappe import _
from frappe.model.rename_doc import get_link_fields, rename_parent_and_child
from frappe.utils.password import remove_encrypted_password

from press_tr.kimlik.accounts import save_authorized_document
from press_tr.kimlik.identity import DELETED_IDENTITY_ISSUER, deleted_identity_subject, find_identity
from press_tr.kimlik.oidc import reject

PROFILE_FIELDS = (
	"gender",
	"last_ip",
	"reset_password_key",
	"short_bio",
)
COMMUNICATION_BODIES = ("content", "text_content")
PRIVATE_CHILDREN = ("User Social Login", "User Email")
RECORD_PAGE_SIZE = 100


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
	for row in iter_named_rows("Press Keycloak Session", {"identity_link": identity_link}):
		remove_encrypted_password("Press Keycloak Session", row.name, "press_sid")
	frappe.db.delete("Press Keycloak Session", {"identity_link": identity_link})


def redact_profile(profile, placeholder: str) -> None:
	user = profile.name
	email = profile.email
	redact_email_queue(email, placeholder)
	for field in ("cc", "bcc"):
		redact_address_lists("Communication", field, email, placeholder, dict.fromkeys(COMMUNICATION_BODIES))

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
		if doctype == "Communication" and field in {"sender", "recipients"}:
			redactions = dict.fromkeys((*COMMUNICATION_BODIES, *spec.get("redact_fields", ())))
			redact_address_lists(doctype, field, email, placeholder, redactions)
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
		if (doctype, field) == ("Email Unsubscribe", "email"):
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
		for row in iter_named_rows("User 2FA", {"user": user}):
			remove_encrypted_password("User 2FA", row.name, "totp_secret")
			frappe.db.delete("User 2FA", {"name": row.name})

	frappe.db.set_value(
		"Activity Log",
		{"user": user},
		{"full_name": "Deleted", "subject": "Account activity", "ip_address": None},
		update_modified=False,
	)
	frappe.db.delete("Version", {"ref_doctype": "User", "docname": user})

	personal_files = get_personal_files(user, profile.user_image)
	clean_press_ownership(user)
	frappe.db.delete(
		"Comment",
		{
			"reference_doctype": "User",
			"reference_name": user,
			"comment_type": ["in", ["Attachment", "Attachment Removed"]],
		},
	)
	rename_linked_record("User", user, placeholder)
	for doctype in ("Comment", "Communication"):
		replace_link_by_primary_key(
			doctype, {"reference_doctype": "User", "reference_name": user}, "reference_name", placeholder
		)
	redact_record_ownership(user, placeholder)
	# File hooks unlink local data immediately. Run the table scan before them.
	for name in sorted(personal_files):
		frappe.delete_doc("File", name, ignore_permissions=True, delete_permanently=True)
	frappe.db.after_commit.add(lambda: clear_session_cache(user, ()))


def get_personal_files(user: str, image: str | None) -> set[str]:
	queries = [
		{"attached_to_doctype": "User", "attached_to_name": user},
		{"owner": user, "attached_to_doctype": ["is", "not set"], "attached_to_name": ["is", "not set"]},
	]
	if image:
		queries.append({"owner": user, "file_url": image, "attached_to_doctype": ["is", "not set"]})
	# Frappe flattens or_filters into individual OR terms. Each scope needs AND.
	return {row.name for filters in queries for row in iter_named_rows("File", {"is_folder": 0, **filters})}


def redact_address_lists(
	doctype: str, field: str, email: str, placeholder: str, redactions: dict | None = None
) -> set[str]:
	matched = set()
	for row in iter_named_rows(doctype, {field: ["like", f"%{email}%"]}, (field,)):
		if redacted := replace_mailbox(row[field], email, placeholder):
			frappe.db.set_value(
				doctype, row.name, {**(redactions or {}), field: redacted}, update_modified=False
			)
			matched.add(row.name)
	return matched


def iter_named_rows(doctype: str, filters: dict, fields: tuple[str, ...] = ()):
	while rows := frappe.get_all(
		doctype, filters=filters, fields=["name", *fields], order_by="name asc", limit=RECORD_PAGE_SIZE
	):
		yield from rows
		if len(rows) < RECORD_PAGE_SIZE:
			return
		# The key cursor remains valid when consumers change or delete a returned row.
		filters = {**filters, "name": [">", rows[-1].name]}


def replace_mailbox(value: str, email: str, placeholder: str) -> str | None:
	addresses = getaddresses([value])
	email = email.lower()
	if not any(address.lower() == email for _, address in addresses):
		return None
	return ", ".join(
		placeholder if address.lower() == email else formataddr((name, address))
		for name, address in addresses
	)


def redact_email_queue(email: str, placeholder: str) -> None:
	queues = redact_address_lists("Email Queue", "sender", email, placeholder)
	queues.update(redact_address_lists("Email Queue", "show_as_cc", email, placeholder))
	for row in iter_named_rows(
		"Email Queue Recipient",
		{"parenttype": "Email Queue", "recipient": ["like", f"%{email}%"]},
		("parent", "recipient"),
	):
		if redacted := replace_mailbox(row.recipient, email, placeholder):
			frappe.db.set_value(
				"Email Queue Recipient", row.name, "recipient", redacted, update_modified=False
			)
			queues.add(row.parent)
	for name in sorted(queues):
		frappe.db.set_value("Email Queue", name, "message", None, update_modified=False)
		# Frappe otherwise retries pending mail with an empty body.
		frappe.db.set_value(
			"Email Queue",
			{"name": name, "status": ["in", ["Not Sent", "Partially Sent"]]},
			{
				"status": "Error",
				"error": _("Message cleared after account anonymization.", context="press_tr"),
			},
			update_modified=False,
		)


def redact_user_contacts(
	user: str, email: str, placeholder: str, fields: set[str], address_fields: set[str]
) -> None:
	contacts = {row.name for row in iter_named_rows("Contact", {"user": user})}
	contacts.update(row.name for row in iter_named_rows("Contact", {"email_id": email}))
	contacts.update(
		row.parent
		for row in iter_named_rows("Contact Email", {"email_id": email, "parenttype": "Contact"}, ("parent",))
	)
	addresses = {row.name for row in iter_named_rows("Address", {"email_id": email})}
	for link_doctype, names in (("User", [user]), ("Contact", sorted(contacts))):
		for batch in batched(names, RECORD_PAGE_SIZE, strict=False):
			addresses.update(
				row.parent
				for row in iter_named_rows(
					"Dynamic Link",
					{"parenttype": "Address", "link_doctype": link_doctype, "link_name": ["in", list(batch)]},
					("parent",),
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
		for row in iter_named_rows("User SSH Key", {"user": user}):
			frappe.delete_doc("User SSH Key", row.name, ignore_permissions=True)

	teams = {
		row.parent
		for row in iter_named_rows("Team Member", {"user": user, "parenttype": "Team"}, ("parent",))
	}
	teams.update(row.name for row in iter_named_rows("Team", {"user": user}))
	for team in sorted(teams):
		owner = frappe.db.get_value("Team", team, "user", for_update=True)
		members = {
			row.user
			for row in iter_named_rows("Team Member", {"parenttype": "Team", "parent": team}, ("user",))
		}
		if owner == user:
			frappe.db.set_value(
				"Team", team, {"billing_name": None, "phone_number": None}, update_modified=False
			)
			for version in iter_named_rows("Version", {"ref_doctype": "Team", "docname": team}, ("data",)):
				data = frappe.parse_json(version.data)
				changes = data.get("changed", [])
				cleaned = [change for change in changes if change[0] not in {"billing_name", "phone_number"}]
				if cleaned != changes:
					data["changed"] = cleaned
					frappe.db.set_value(
						"Version", version.name, "data", frappe.as_json(data), update_modified=False
					)

		if members == {user} or (not members and owner == user):
			frappe.db.set_value("Team", team, "enabled", 0, update_modified=False)
			for row in iter_named_rows(
				"Site", {"team": team, "status": ["not in", ["Archived", "Suspended"]]}
			):
				site = frappe.get_doc("Site", row.name, for_update=True)
				site.suspend(reason="Account anonymized")
				# Account deletion authorizes suspension only for this sole-member team's sites.
				save_authorized_document(site)


def rename_linked_record(doctype: str, old: str, new: str) -> None:
	# Use exact Frappe links without rename hooks, edit comments or realtime events.
	# Invoice is a legal record.
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


def redact_record_ownership(user: str, placeholder: str) -> None:
	# Standard ownership columns are physical columns, not Frappe Link fields.
	columns = frappe.qb.Schema("information_schema").columns
	ownership_columns = (
		frappe.qb.from_(columns)
		.select(columns.table_name, columns.column_name)
		.where(columns.table_schema == frappe.db.cur_db_name)
		.where(columns.table_name.like("tab%"))
		.where(
			columns.table_name.notin(
				(
					"tabInvoice",
					"tabInvoice Item",
					"tabInvoice Credit Allocation",
					"tabInvoice Transaction Fee",
					"tabInvoice Discount",
				)
			)
		)
		.where(columns.column_name.isin(("owner", "modified_by")))
		.orderby(columns.table_name, columns.column_name)
		.run()
	)
	for table_name, rows in groupby(ownership_columns, key=itemgetter(0)):
		table = frappe.qb.Table(table_name)
		fields = [table[field] for _, field in rows]
		matches = fields[0] == user
		for field in fields[1:]:
			matches |= field == user
		# Check both columns in one scan. Physical metadata avoids fetching each DocType.
		query = (
			frappe.qb.from_(table)
			.select(table.name)
			.where(matches)
			.orderby(table.name)
			.limit(RECORD_PAGE_SIZE)
		)
		page = query
		names = page.run(pluck=True)
		if not names:
			continue
		frappe.clear_document_cache(table_name.removeprefix("tab"))
		while names:
			for field in fields:
				(
					frappe.qb.update(table)
					.set(field, placeholder)
					.where((field == user) & table.name.isin(names))
					.run()
				)
			if len(names) < RECORD_PAGE_SIZE:
				break
			names = query.where(table.name > names[-1]).run(pluck=True)


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
