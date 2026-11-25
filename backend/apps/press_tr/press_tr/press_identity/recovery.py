"""Account recovery review records (G-163).

A recovery request only opens a review record. It never changes Keycloak credentials,
sends a sign-in link or creates a session. A reviewer who is not the account owner
approves or rejects the record with a note. A lost key is replaced only after approval.

After approval, the key removal step in `recovery_keys` removes the old keys (AJA-420). That step
alone moves the record to Removal Failed or Completed. A desk form or API write cannot.
"""

import frappe
from frappe import _

REVIEW_DOCTYPE = "PTR Recovery Review"
OPEN = "Open"
APPROVED = "Approved"
DECISIONS = (APPROVED, "Rejected")
# AJA-420: after approval, the key removal step moves the record on. Only that step writes these.
REMOVAL_FAILED = "Removal Failed"
COMPLETED = "Completed"
REMOVAL_STATES = (REMOVAL_FAILED, COMPLETED)
REMOVAL_STEPS = {APPROVED: REMOVAL_STATES, REMOVAL_FAILED: REMOVAL_STATES}
FINAL = ("Rejected", COMPLETED)
MAX_EMAIL_LENGTH = 254


def open_review(email: str) -> None:
	address = (email or "").strip().lower()
	if not address or len(address) > MAX_EMAIL_LENGTH or "@" not in address:
		return
	user = frappe.db.get_value("User", {"email": address}, "name")
	if not user:
		return
	link = frappe.db.get_value("PTR Identity Link", {"user": user}, "name")
	if not link:
		return
	if frappe.db.exists(REVIEW_DOCTYPE, {"identity_link": link, "status": OPEN}):
		return
	frappe.get_doc(
		{
			"doctype": REVIEW_DOCTYPE,
			"identity_link": link,
			"status": OPEN,
			"requested_at": frappe.utils.now_datetime(),
		}
	).insert(ignore_permissions=True)


REVIEW_FIELDS = ("identity_link", "requested_at", "review_note", "reviewed_by", "reviewed_at")
# Only the key removal step writes these (AJA-420).
REMOVAL_FIELDS = ("removal_attempted_at", "removal_error", "completed_at")
FIELDS = ("status", *REVIEW_FIELDS, *REMOVAL_FIELDS)
# Only the decision step writes these. An API write cannot set them on an open record.
FIXED_WHILE_OPEN = ("identity_link", "requested_at", "reviewed_by", "reviewed_at", *REMOVAL_FIELDS)


DATETIME_FIELDS = ("requested_at", "reviewed_at", "removal_attempted_at", "completed_at")


def _value(record, field):
	# The database gives a datetime. An API client may send the same moment as
	# "2026-11-20 10:00:00" or as "2026-11-20T10:00:00", so dates compare by value.
	value = getattr(record, field, None)
	if value is None or value == "":
		return None
	if field in DATETIME_FIELDS:
		try:
			return frappe.utils.get_datetime(value)
		except (TypeError, ValueError, OverflowError):
			# An unreadable date never matches a stored one.
			return str(value)
	return str(value)


def _changed(doc, previous, fields):
	return [field for field in fields if _value(doc, field) != _value(previous, field)]


def _check_key_removal(doc, previous) -> None:
	# The removal step may only change the state and its own fields. The decision stays as it was.
	if doc.status not in REMOVAL_STEPS.get(previous.status, ()) or _changed(doc, previous, REVIEW_FIELDS):
		frappe.throw(_("A recovery review decision is final.", context="press_tr"), frappe.PermissionError)


def check_decision(doc) -> None:
	# Frappe applies read_only only in the desk form. This check also guards API writes.
	previous = doc.get_doc_before_save()
	if previous is None:
		if doc.status != OPEN or any(_value(doc, field) for field in ("reviewed_by", "reviewed_at", *REMOVAL_FIELDS)):
			frappe.throw(_("A recovery review starts open.", context="press_tr"), frappe.PermissionError)
		return
	if previous.status != OPEN:
		if previous.status not in FINAL and getattr(getattr(doc, "flags", None), "key_removal", False):
			_check_key_removal(doc, previous)
			return
		if _changed(doc, previous, FIELDS):
			frappe.throw(
				_("A recovery review decision is final.", context="press_tr"), frappe.PermissionError
			)
		return
	if _changed(doc, previous, FIXED_WHILE_OPEN):
		frappe.throw(
			_("Only the decision step fills the review fields.", context="press_tr"), frappe.PermissionError
		)
	if doc.status == previous.status:
		return
	if doc.status not in DECISIONS:
		frappe.throw(_("Choose Approved or Rejected.", context="press_tr"), frappe.PermissionError)
	reviewer = frappe.session.user
	owner = frappe.db.get_value("PTR Identity Link", doc.identity_link, "user")
	if reviewer in ("Guest", owner):
		frappe.throw(
			_("The account owner cannot review their own recovery request.", context="press_tr"),
			frappe.PermissionError,
		)
	if not (doc.review_note or "").strip():
		frappe.throw(_("Write a review note before you decide.", context="press_tr"), frappe.PermissionError)
	doc.reviewed_by = reviewer
	doc.reviewed_at = frappe.utils.now_datetime()
