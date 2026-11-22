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
from collections.abc import Iterator
from email.utils import getaddresses, parseaddr
from itertools import batched, chain

import frappe

REDACTED = "[REDACTED]"
# P-3: growing lists are read page by page with a stable order.
PAGE_SIZE = 500
# Rows that `_extra_records` handles with the own or shared distinction (merge review 2, E3).
HANDLED_BY_OWNERSHIP = frozenset(("Contact", "Contact Email", "Address", "File", "Communication"))
TEXT_TYPES = frozenset(
	("Data", "Small Text", "Text", "Long Text", "Text Editor", "Code", "HTML Editor", "Markdown Editor")
)
EMPTY_TYPES = frozenset(("Date", "Datetime", "Time", "Attach", "Attach Image", "Phone", "Int", "Float"))


def _rows(
	doctype: str,
	*,
	filters: dict | None = None,
	fields: list[str] | None = None,
	pluck: str | None = None,
	or_filters: dict | None = None,
) -> Iterator:
	"""Reads bounded pages by name so updates to matching rows cannot shift later pages.

	G-3: the identity-sync deletion runs as Administrator and selects fields by
	the deleted account's identifiers (docs/sozlesmeler.md section 7).
	"""
	filters = dict(filters or {})
	projection = list(dict.fromkeys(["name", *(fields or []), *([pluck] if pluck else [])]))
	fixed_name = "name" in filters
	while True:
		page = frappe.get_all(
			doctype,
			filters=filters,
			or_filters=or_filters,
			fields=projection,
			order_by="name asc",
			limit=PAGE_SIZE,
		)
		for row in page:
			yield row[pluck] if pluck else row
		if fixed_name or len(page) < PAGE_SIZE:
			return
		filters["name"] = (">", page[-1]["name"])


def scrub_after_rename(user: str, anon: str) -> None:
	"""Redacts the address in Edit comments on records renamed by Frappe's User hooks.

	Frappe 16.56.0 writes the rename note as an Edit comment (model/rename_doc.py:206).
	User.after_rename also renames the user's Notification Settings (user.py:745).
	"""
	for row in _rows(
		"Comment",
		filters={
			"reference_doctype": ("in", ("User", "Notification Settings")),
			"reference_name": anon,
			"comment_type": "Edit",
			"content": ("like", f"%{user}%"),
		},
		fields=["name", "content"],
	):
		content = _scrub(row.content, user, anon, "")
		if content != row.content:
			frappe.db.set_value("Comment", row.name, "content", content, update_modified=False)


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

	A Contact is the person's own when it is linked to no business record and every e-mail row is the
	person's exact address (or it has no e-mail row and its `user` field is the person). A Contact that also
	lists another address, or that is linked to a business record, is shared. An Address is the
	person's own when every link points to the person's own Contacts, or when it has no link and its
	e-mail is the person's address. Shared records keep the other people's data.
	"""
	candidates = set(_rows("Contact Email", filters={"email_id": user}, pluck="parent"))
	user_contacts = set()
	for row in _rows("Contact", filters={"user": user}, fields=["user"]):
		candidates.add(row.name)
		if row.user == user:
			user_contacts.add(row.name)
	addresses = set(_rows("Address", filters={"email_id": user}, pluck="name"))
	addresses.update(
		_rows(
			"Dynamic Link",
			filters={"parenttype": "Address", "link_doctype": "User", "link_name": user},
			pluck="parent",
		)
	)
	own_contacts = set()

	for batch in batched(candidates, PAGE_SIZE, strict=False):
		contacts_with_email, contacts_with_other_email = set(), set()
		for row in _rows(
			"Contact Email",
			filters={"parent": ("in", batch), "parenttype": "Contact"},
			fields=["parent", "email_id"],
		):
			contacts_with_email.add(row.parent)
			if not _same_address(row.email_id, user):
				contacts_with_other_email.add(row.parent)
		business_contacts = set(
			_rows(
				"Dynamic Link",
				filters={"parent": ("in", batch), "parenttype": "Contact", "link_doctype": ("!=", "User")},
				pluck="parent",
			)
		)
		eligible_contacts = contacts_with_email | user_contacts.intersection(batch)
		own_contacts.update(eligible_contacts - contacts_with_other_email - business_contacts)
		addresses.update(
			_rows(
				"Dynamic Link",
				filters={"link_doctype": "Contact", "link_name": ("in", batch), "parenttype": "Address"},
				pluck="parent",
			)
		)

	shared_addresses = set()
	for batch in batched(addresses, PAGE_SIZE, strict=False):
		for link in _rows(
			"Dynamic Link",
			filters={"parent": ("in", batch), "parenttype": "Address"},
			fields=["parent", "link_doctype", "link_name"],
		):
			if link.link_doctype == "User" and link.link_name == user:
				continue
			if link.link_doctype != "Contact" or link.link_name not in own_contacts:
				shared_addresses.add(link.parent)
	return frappe._dict(
		contacts=own_contacts,
		shared_contacts=candidates - own_contacts,
		addresses=addresses - shared_addresses,
		shared_addresses=shared_addresses,
	)


def _shared(owned: frappe._dict, doctype: str, name: str) -> bool:
	return (doctype == "Contact" and name in owned.shared_contacts) or (
		doctype == "Address" and name in owned.shared_addresses
	)


def _bound_rows(doctype: str, filter_by: str, user: str, fields: list[str]) -> Iterator:
	meta = frappe.get_meta(doctype)
	if filter_by not in ("owner", "name") and not meta.get_field(filter_by):
		return
	yield from _rows(doctype, filters={filter_by: user}, fields=fields)


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
	"""Merge review 3: the list is read with e-mail header rules (`email.utils.getaddresses`), so a quoted
	name with a comma is one recipient. Only the matching recipient changes, name and address. The other
	recipients keep their exact text, spaces included.
	"""
	if not isinstance(value, str) or not value:
		return value
	parts = _split_recipients(value)
	changed = False
	for index, part in enumerate(parts):
		if part.strip() and any(_same_address(address, user) for _name, address in getaddresses([part])):
			lead = part[: len(part) - len(part.lstrip())]
			parts[index] = f"{lead}{anon}"
			changed = True
	return ",".join(parts) if changed else value


def _split_recipients(value: str) -> list[str]:
	"""Splits on commas outside quotes, comments and angle brackets. Each part keeps its own spacing."""
	parts, current, quoted, depth, angle, escaped = [], [], False, 0, False, False
	for char in value:
		if escaped:
			escaped = False
		elif char == "\\" and quoted:
			escaped = True
		elif char == '"' and depth == 0:
			quoted = not quoted
		elif not quoted and char == "(":
			depth += 1
		elif not quoted and char == ")" and depth:
			depth -= 1
		elif not quoted and depth == 0 and char == "<":
			angle = True
		elif not quoted and depth == 0 and char == ">":
			angle = False
		elif char == "," and not quoted and depth == 0 and not angle:
			parts.append("".join(current))
			current = []
			continue
		current.append(char)
	parts.append("".join(current))
	return parts


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
	_clear_shared_contacts(owned.shared_contacts, user)
	for address in owned.addresses:
		_blank_address(address)
	# Shared addresses lose only the person's e-mail.
	for batch in batched(owned.shared_addresses, PAGE_SIZE, strict=False):
		for row in _rows("Address", filters={"name": ("in", batch)}, fields=["email_id"]):
			if _same_address(row.email_id, user):
				frappe.db.set_value("Address", row.name, "email_id", None, update_modified=False)

	# Activity Log: name and IP address.
	for row in chain(
		_rows("Activity Log", filters={"user": user}, fields=["subject", "full_name"]),
		_rows("Activity Log", filters={"owner": user}, fields=["subject", "full_name"]),
	):
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
	for row in _rows(
		"Version",
		filters={"ref_doctype": ("in", ("User", "Contact")), "docname": ("in", [user, *contacts])},
		pluck="name",
	):
		frappe.db.set_value("Version", row, "data", json.dumps({"redacted": True}), update_modified=False)
	for row in _rows("Version", filters={"owner": user}, fields=["name", "data"]):
		scrubbed = _scrub(row["data"], user, anon, full_name)
		if scrubbed != row["data"]:
			frappe.db.set_value("Version", row["name"], "data", scrubbed, update_modified=False)

	# Personal files (merge review E3): files bound to the User record or to the person's own records
	# (Contact). A file on a business record is a business record and stays, whoever uploaded it.
	files = set(
		_rows("File", filters={"attached_to_doctype": "User", "attached_to_name": user}, pluck="name")
	)
	if contacts:
		files |= set(
			_rows(
				"File",
				filters={"attached_to_doctype": "Contact", "attached_to_name": ("in", list(contacts))},
				pluck="name",
			)
		)
	for name in files:
		file = frappe.get_doc("File", name)
		frappe.delete_doc("File", name, force=True, delete_permanently=True)
		# File.on_trash schedules disk cleanup and writes the filename into a timeline comment.
		frappe.db.delete(
			"Comment",
			{
				"reference_doctype": file.attached_to_doctype,
				"reference_name": file.attached_to_name,
				"comment_type": "Attachment Removed",
				"content": file.file_name,
			},
		)
	frappe.db.set_value("User", user, {"user_image": None, "banner_image": None}, update_modified=False)

	# Communication and the e-mail queue.
	for row in _rows(
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
			values.update(sender_full_name=REDACTED, phone_no=None, content=REDACTED)
		if values:
			frappe.db.set_value("Communication", row["name"], values, update_modified=False)
	for row in _rows("Email Queue", filters={"sender": ("like", f"%{user}%")}, fields=["name", "sender"]):
		scrubbed = _replace_in_address_list(row["sender"], user, anon)
		if scrubbed != row["sender"]:
			frappe.db.set_value("Email Queue", row["name"], "sender", scrubbed, update_modified=False)
	for row in _rows("Email Queue Recipient", filters={"recipient": user}, pluck="name"):
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


def _clear_shared_contacts(contacts: set[str], user: str) -> None:
	"""Removes only the deleted account's addresses from the shared contacts."""
	for batch in batched(contacts, PAGE_SIZE, strict=False):
		remaining = {}
		for row in _rows(
			"Contact Email",
			filters={"parent": ("in", batch), "parenttype": "Contact"},
			fields=["parent", "email_id"],
		):
			if _same_address(row.email_id, user):
				frappe.db.delete("Contact Email", {"name": row.name})
			else:
				remaining.setdefault(row.parent, row.email_id)
		for row in _rows("Contact", filters={"name": ("in", batch)}, fields=["user", "email_id"]):
			values = {}
			if row.user == user:
				values["user"] = None
			if _same_address(row.email_id, user):
				values["email_id"] = remaining.get(row.name)
			if values:
				frappe.db.set_value("Contact", row.name, values, update_modified=False)


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
