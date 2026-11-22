"""What account deletion anonymizes (docs/sozlesmeler.md section 7, anonymization rules 4 and 5).

The scope comes from the `user_data_fields` hooks of every installed app, plus the extra records listed in
the contract. Only rows bound to the user change:

- an entry with `redact_fields` changes those fields in rows where `filter_by` (default `owner`) is the user,
- an entry without `redact_fields` replaces the user's e-mail and full name in the text fields of rows
  where `filter_by` is the user. Frappe's “strict” mode would scan every row of the table for the full
  name (personal_data_deletion_request.py:317), which can change another person with the same name.
  Here a strict entry is limited to rows owned by the user.

Rows are read with `frappe.get_all` and written with `frappe.db.set_value` (no raw SQL, ai-readiness rule).
The caller renames the user afterwards; Frappe then rewrites every Link, `owner` and `modified_by` value
(frappe/core/doctype/user/user.py:732).
"""

import json
import re
from email.utils import parseaddr

import frappe

REDACTED = "[REDACTED]"
# Rows that `_extra_records` handles with the own or shared distinction (merge review 2, E3).
HANDLED_BY_OWNERSHIP = frozenset(("Contact", "Contact Email", "Address"))
TEXT_TYPES = frozenset(
	("Data", "Small Text", "Text", "Long Text", "Text Editor", "Code", "HTML Editor", "Markdown Editor")
)
EMPTY_TYPES = frozenset(("Date", "Datetime", "Time", "Attach", "Attach Image", "Phone", "Int", "Float"))


def anonymize(user: str, anon: str) -> None:
	full_name = frappe.db.get_value("User", user, "full_name") or ""
	owned = _ownership(user)
	for ref in frappe.get_hooks("user_data_fields"):
		doctype = ref.get("doctype")
		if not doctype or doctype in HANDLED_BY_OWNERSHIP or not frappe.db.exists("DocType", doctype):
			continue
		if ref.get("redact_fields"):
			_redact_fields(ref, user, anon, owned)
		else:
			_replace_in_bound_rows(ref, user, anon, full_name)
	_extra_records(user, anon, full_name, owned)


def _ownership(user: str) -> frappe._dict:
	"""Separates the person's own Contact and Address records from shared ones (merge review 2, E3).

	A Contact is the person's own when every e-mail row is the person's exact address, or when it has no
	e-mail row and its `user` field is the person. A Contact that also lists another address is shared. An Address is the
	person's own when every link points to the person's own Contacts, or when it has no link and its
	e-mail is the person's address. Shared records keep the other people's data.
	"""
	candidates = set(frappe.get_all("Contact", filters={"user": user}, pluck="name"))
	candidates |= set(frappe.get_all("Contact Email", filters={"email_id": user}, pluck="parent"))
	own_contacts, shared_contacts = set(), set()
	for name in candidates:
		addresses = frappe.get_all(
			"Contact Email", filters={"parent": name, "parenttype": "Contact"}, pluck="email_id"
		)
		# Frappe fills `user` from the primary e-mail by itself, so that field is not an explicit tie.
		# The e-mail rows decide: every address is the person's, or there is no address and `user` points
		# to the person.
		if (addresses and all(_same_address(address, user) for address in addresses)) or (
			not addresses and frappe.db.get_value("Contact", name, "user") == user
		):
			own_contacts.add(name)
		else:
			shared_contacts.add(name)
	address_names = set(frappe.get_all("Address", filters={"email_id": user}, pluck="name"))
	for contact in candidates:
		address_names |= set(
			frappe.get_all(
				"Dynamic Link",
				filters={"link_doctype": "Contact", "link_name": contact, "parenttype": "Address"},
				pluck="parent",
			)
		)
	own_addresses, shared_addresses = set(), set()
	for name in address_names:
		links = frappe.get_all(
			"Dynamic Link",
			filters={"parent": name, "parenttype": "Address"},
			fields=["link_doctype", "link_name"],
		)
		if all(link.link_doctype == "Contact" and link.link_name in own_contacts for link in links):
			own_addresses.add(name)
		else:
			shared_addresses.add(name)
	return frappe._dict(
		contacts=own_contacts,
		shared_contacts=shared_contacts,
		addresses=own_addresses,
		shared_addresses=shared_addresses,
	)


def _shared(owned: frappe._dict, doctype: str, name: str) -> bool:
	return (doctype == "Contact" and name in owned.shared_contacts) or (
		doctype == "Address" and name in owned.shared_addresses
	)


def _bound_rows(doctype: str, filter_by: str, user: str, fields: list[str]) -> list[dict]:
	meta = frappe.get_meta(doctype)
	if filter_by not in ("owner", "name") and not meta.get_field(filter_by):
		return []
	return frappe.get_all(doctype, filters={filter_by: user}, fields=["name", *fields])


def _value_for(df, anon: str):
	if df.unique or df.options == "Email":
		return anon
	if df.fieldtype in EMPTY_TYPES:
		return 0 if df.fieldtype in ("Int", "Float") else None
	return REDACTED


def _redact_fields(ref: dict, user: str, anon: str, owned: frappe._dict) -> None:
	doctype = ref["doctype"]
	meta = frappe.get_meta(doctype)
	fields = [f for f in ref["redact_fields"] if meta.get_field(f)]
	if not fields:
		return
	values = {f: _value_for(meta.get_field(f), anon) for f in fields}
	filter_by = ref.get("filter_by", "owner")
	rows = [
		row for row in _bound_rows(doctype, filter_by, user, []) if not _shared(owned, doctype, row["name"])
	]
	for index, row in enumerate(rows):
		frappe.db.set_value(doctype, row["name"], values, update_modified=False)
		if ref.get("rename") and doctype != "User" and row["name"] != anon:
			new_name = anon if index == 0 else f"{anon}-{index}"
			if not frappe.db.exists(doctype, new_name):
				frappe.rename_doc(doctype, row["name"], new_name, force=True, show_alert=False)


def _text_fields(doctype: str) -> list[str]:
	return [df.fieldname for df in frappe.get_meta(doctype).fields if df.fieldtype in TEXT_TYPES]


# Characters allowed in the local part of an address (RFC 5322 atext) plus the dot. An address preceded or
# followed by one of them is another address, for example `x.<address>`, `team'<address>` or `<address>.tr`.
_ADDRESS_CHARS = r"A-Za-z0-9!#$%&'*+/=?^_`{|}~.-"


def _address_pattern(address: str) -> re.Pattern:
	"""Merge review E3: only the exact address matches."""
	return re.compile(rf"(?<![{_ADDRESS_CHARS}]){re.escape(address)}(?![{_ADDRESS_CHARS}])", re.IGNORECASE)


def _same_address(value, user: str) -> bool:
	return isinstance(value, str) and parseaddr(value)[1].strip().lower() == user.lower()


def _replace_in_address_list(value, user: str, anon: str):
	"""Address fields are parsed one by one. Only an entry whose address equals the user's changes."""
	if not isinstance(value, str) or not value:
		return value
	parts = [part.strip() for part in value.split(",")]
	return ", ".join(anon if _same_address(part, user) else part for part in parts)


def _scrub(text, user: str, anon: str, full_name: str):
	if not isinstance(text, str) or not text:
		return text
	result = _address_pattern(user).sub(anon, text)
	if full_name and full_name != user:
		result = result.replace(full_name, REDACTED)
	return result


def _replace_in_bound_rows(ref: dict, user: str, anon: str, full_name: str) -> None:
	doctype = ref["doctype"]
	fields = _text_fields(doctype)
	if not fields:
		return
	filter_by = "owner" if ref.get("strict") else ref.get("filter_by", "owner")
	for row in _bound_rows(doctype, filter_by, user, fields):
		changed = {f: _scrub(row[f], user, anon, full_name) for f in fields}
		changed = {f: v for f, v in changed.items() if v != row[f]}
		if changed:
			frappe.db.set_value(doctype, row["name"], changed, update_modified=False)


def _extra_records(user: str, anon: str, full_name: str, owned: frappe._dict) -> None:
	"""Contract rule 4: records that the hooks do not cover, or cover only partly."""
	contacts = owned.contacts
	# The person's own Contacts, with their e-mail and phone rows.
	for name in contacts:
		frappe.db.delete("Contact Email", {"parent": name, "parenttype": "Contact"})
		frappe.db.delete("Contact Phone", {"parent": name, "parenttype": "Contact"})
		frappe.db.set_value(
			"Contact",
			name,
			{
				"first_name": REDACTED,
				"middle_name": None,
				"last_name": None,
				"full_name": REDACTED,
				"email_id": None,
				"phone": None,
				"mobile_no": None,
				"image": None,
				"user": None,
			},
			update_modified=False,
		)
	# Shared Contacts lose only the person's own e-mail rows.
	for name in owned.shared_contacts:
		for row in frappe.get_all(
			"Contact Email", filters={"parent": name, "parenttype": "Contact"}, fields=["name", "email_id"]
		):
			if _same_address(row.email_id, user):
				frappe.db.delete("Contact Email", {"name": row.name})
		if frappe.db.get_value("Contact", name, "user") == user:
			frappe.db.set_value("Contact", name, "user", None, update_modified=False)
		if _same_address(frappe.db.get_value("Contact", name, "email_id"), user):
			remaining = frappe.get_all(
				"Contact Email", filters={"parent": name, "parenttype": "Contact"}, pluck="email_id", limit=1
			)
			frappe.db.set_value(
				"Contact", name, "email_id", remaining[0] if remaining else None, update_modified=False
			)
	for address in owned.addresses:
		_blank_address(address)
	# Shared addresses lose only the person's e-mail.
	for address in owned.shared_addresses:
		if _same_address(frappe.db.get_value("Address", address, "email_id"), user):
			frappe.db.set_value("Address", address, "email_id", None, update_modified=False)

	# Activity Log: name and IP address.
	for row in frappe.get_all(
		"Activity Log", filters={"user": user}, fields=["name", "subject", "full_name"]
	) + frappe.get_all("Activity Log", filters={"owner": user}, fields=["name", "subject", "full_name"]):
		frappe.db.set_value(
			"Activity Log",
			row["name"],
			{
				"full_name": REDACTED,
				"ip_address": None,
				"subject": _scrub(row["subject"], user, anon, full_name),
			},
			update_modified=False,
		)

	# Version: old personal values of the user's own records and of records the user changed.
	for row in frappe.get_all(
		"Version",
		filters={"ref_doctype": ("in", ("User", "Contact")), "docname": ("in", [user, *contacts])},
		pluck="name",
	):
		frappe.db.set_value("Version", row, "data", json.dumps({"redacted": True}), update_modified=False)
	for row in frappe.get_all("Version", filters={"owner": user}, fields=["name", "data"]):
		scrubbed = _scrub(row["data"], user, anon, full_name)
		if scrubbed != row["data"]:
			frappe.db.set_value("Version", row["name"], "data", scrubbed, update_modified=False)

	# Personal files (merge review E3): files bound to the User record or to the person's own records
	# (Contact). A file on a business record is a business record and stays, whoever uploaded it.
	files = set(
		frappe.get_all(
			"File", filters={"attached_to_doctype": "User", "attached_to_name": user}, pluck="name"
		)
	)
	if contacts:
		files |= set(
			frappe.get_all(
				"File",
				filters={"attached_to_doctype": "Contact", "attached_to_name": ("in", list(contacts))},
				pluck="name",
			)
		)
	for name in files:
		frappe.delete_doc("File", name, force=True, ignore_permissions=True)
	frappe.db.set_value("User", user, {"user_image": None, "banner_image": None}, update_modified=False)

	# Communication and the e-mail queue.
	for row in frappe.get_all(
		"Communication",
		or_filters={
			"sender": user,
			"recipients": ("like", f"%{user}%"),
			"cc": ("like", f"%{user}%"),
			"bcc": ("like", f"%{user}%"),
		},
		fields=["name", "sender", "sender_full_name", "recipients", "cc", "bcc"],
	):
		values = {
			f: _replace_in_address_list(row[f], user, anon) for f in ("sender", "recipients", "cc", "bcc")
		}
		values = {f: v for f, v in values.items() if v != row[f]}
		if (row["sender"] or "").lower() == user.lower():
			values["sender_full_name"] = REDACTED
		if values:
			frappe.db.set_value("Communication", row["name"], values, update_modified=False)
	for row in frappe.get_all(
		"Email Queue", filters={"sender": ("like", f"%{user}%")}, fields=["name", "sender"]
	):
		scrubbed = _replace_in_address_list(row["sender"], user, anon)
		if scrubbed != row["sender"]:
			frappe.db.set_value("Email Queue", row["name"], "sender", scrubbed, update_modified=False)
	for row in frappe.get_all("Email Queue Recipient", filters={"recipient": user}, pluck="name"):
		frappe.db.set_value("Email Queue Recipient", row, "recipient", anon, update_modified=False)

	# Two-factor keys, default values, social sign-in rows and extra e-mail rows.
	frappe.db.delete("DefaultValue", {"parent": user})
	for key in (f"{user}_otpsecret", f"{user}_otplogin"):
		frappe.db.delete("DefaultValue", {"defkey": key})
	frappe.db.delete("User Social Login", {"parent": user, "parenttype": "User"})
	frappe.db.delete("User Email", {"parent": user, "parenttype": "User"})

	# Last step: the person's own Contacts are named after the person, so they get anonymous names.
	# Earlier steps used the old names (Contact e-mail rows, Version and files).
	for index, name in enumerate(sorted(contacts)):
		new_name = anon if index == 0 else f"{anon}-{index}"
		if name != new_name and not frappe.db.exists("Contact", new_name):
			frappe.rename_doc("Contact", name, new_name, force=True, show_alert=False)


def _blank_address(name: str) -> None:
	values = {
		field: REDACTED
		for field in ("address_title", "address_line1")
		if frappe.get_meta("Address").get_field(field)
	}
	for field in ("address_line2", "city", "county", "state", "pincode", "phone", "fax", "email_id"):
		if frappe.get_meta("Address").get_field(field):
			values[field] = None
	frappe.db.set_value("Address", name, values, update_modified=False)
