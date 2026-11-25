"""Account recovery review records (G-163).

A recovery request only opens a review record. It never changes Keycloak credentials,
sends a sign-in link or creates a session. A reviewer who is not the account owner
approves or rejects the record with a note. A lost key is replaced only after approval.
"""

import frappe
from frappe import _

REVIEW_DOCTYPE = "PTR Recovery Review"
# AJA-421: only a named person with this role decides. System Manager alone is not enough.
REVIEWER_ROLE = "Recovery Reviewer"
OPEN = "Open"
DECISIONS = ("Approved", "Rejected")
MAX_EMAIL_LENGTH = 254


def request_review(email: str) -> None:
	# The request does the same work for every address. The account lookup and the new
	# record run later in a background job, so the answer time does not show who has an account.
	# The queued address is cut one character past the limit. open_review still rejects it.
	frappe.enqueue(
		"press_tr.press_identity.recovery.open_review",
		queue="short",
		email=(email or "").strip()[: MAX_EMAIL_LENGTH + 1],
	)


def open_review(email: str) -> None:
	# Runs in a background job. The request never waits for this lookup.
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


FIELDS = ("identity_link", "status", "requested_at", "review_note", "reviewed_by", "reviewed_at")
# Only the decision step writes these. An API write cannot set them on an open record.
FIXED_WHILE_OPEN = ("identity_link", "requested_at", "reviewed_by", "reviewed_at")


DATETIME_FIELDS = ("requested_at", "reviewed_at")


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


def require_reviewer(doc) -> str:
	"""Return the session user if they may decide this recovery review, else raise PermissionError.

	DocType permissions can be widened by a System Manager in Role Permissions Manager,
	so the decision step checks the role itself.
	"""
	reviewer = frappe.session.user
	if reviewer in ("Guest", "Administrator"):
		# Administrator gets every role and is a shared account, so the reviewer would not be named.
		frappe.throw(
			_("A named recovery reviewer must make this decision.", context="press_tr"),
			frappe.PermissionError,
		)
	if REVIEWER_ROLE not in frappe.get_roles(reviewer):
		frappe.throw(
			_("Only a Recovery Reviewer can decide a recovery request.", context="press_tr"),
			frappe.PermissionError,
		)
	owner = frappe.db.get_value("PTR Identity Link", doc.identity_link, "user")
	if reviewer == owner:
		frappe.throw(
			_("The account owner cannot review their own recovery request.", context="press_tr"),
			frappe.PermissionError,
		)
	return reviewer


def check_decision(doc) -> None:
	# Frappe applies read_only only in the desk form. This check also guards API writes.
	previous = doc.get_doc_before_save()
	if previous is None:
		if doc.status != OPEN or _value(doc, "reviewed_by") or _value(doc, "reviewed_at"):
			frappe.throw(_("A recovery review starts open.", context="press_tr"), frappe.PermissionError)
		return
	if previous.status in DECISIONS:
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
	reviewer = require_reviewer(doc)
	if not (doc.review_note or "").strip():
		frappe.throw(_("Write a review note before you decide.", context="press_tr"), frappe.PermissionError)
	doc.reviewed_by = reviewer
	doc.reviewed_at = frappe.utils.now_datetime()
