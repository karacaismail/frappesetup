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

import frappe

REDACTED = "[REDACTED]"
TEXT_TYPES = frozenset(
	("Data", "Small Text", "Text", "Long Text", "Text Editor", "Code", "HTML Editor", "Markdown Editor")
)
EMPTY_TYPES = frozenset(("Date", "Datetime", "Time", "Attach", "Attach Image", "Phone", "Int", "Float"))


def anonymize(user: str, anon: str) -> None:
	full_name = frappe.db.get_value("User", user, "full_name") or ""
	for ref in frappe.get_hooks("user_data_fields"):
		doctype = ref.get("doctype")
		if not doctype or not frappe.db.exists("DocType", doctype):
			continue
		if ref.get("redact_fields"):
			_redact_fields(ref, user, anon)
		else:
			_replace_in_bound_rows(ref, user, anon, full_name)
	_extra_records(user, anon, full_name)


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


def _redact_fields(ref: dict, user: str, anon: str) -> None:
	doctype = ref["doctype"]
	meta = frappe.get_meta(doctype)
	fields = [f for f in ref["redact_fields"] if meta.get_field(f)]
	if not fields:
		return
	values = {f: _value_for(meta.get_field(f), anon) for f in fields}
	filter_by = ref.get("filter_by", "owner")
	for index, row in enumerate(_bound_rows(doctype, filter_by, user, [])):
		frappe.db.set_value(doctype, row["name"], values, update_modified=False)
		if ref.get("rename") and doctype != "User" and row["name"] != anon:
			new_name = anon if index == 0 else f"{anon}-{index}"
			if not frappe.db.exists(doctype, new_name):
				frappe.rename_doc(doctype, row["name"], new_name, force=True, show_alert=False)


def _text_fields(doctype: str) -> list[str]:
	return [df.fieldname for df in frappe.get_meta(doctype).fields if df.fieldtype in TEXT_TYPES]


def _address_pattern(address: str) -> re.Pattern:
	"""Merge review E3: only the exact address matches, not `x.<address>` or `<address>.tr`."""
	return re.compile(rf"(?<![A-Za-z0-9._%+-]){re.escape(address)}(?![A-Za-z0-9._%+-])", re.IGNORECASE)


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


def _extra_records(user: str, anon: str, full_name: str) -> None:
	"""Contract rule 4: records that the hooks do not cover, or cover only partly."""
	# Contacts bound to the user, with their e-mail and phone rows.
	contacts = set(frappe.get_all("Contact", filters={"user": user}, pluck="name"))
	contacts |= set(frappe.get_all("Contact Email", filters={"email_id": user}, pluck="parent"))
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
		for address in frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Contact", "link_name": name, "parenttype": "Address"},
			pluck="parent",
		):
			_blank_address(address)
	for address in frappe.get_all("Address", filters={"email_id": user}, pluck="name"):
		_blank_address(address)

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
		values = {f: _scrub(row[f], user, anon, "") for f in ("sender", "recipients", "cc", "bcc")}
		values = {f: v for f, v in values.items() if v != row[f]}
		if (row["sender"] or "").lower() == user.lower():
			values["sender_full_name"] = REDACTED
		if values:
			frappe.db.set_value("Communication", row["name"], values, update_modified=False)
	for row in frappe.get_all(
		"Email Queue", filters={"sender": ("like", f"%{user}%")}, fields=["name", "sender"]
	):
		scrubbed = _scrub(row["sender"], user, anon, "")
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
