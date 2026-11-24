"""Account recovery review records (G-163).

A recovery request only opens a review record. It never changes Keycloak credentials,
sends a sign-in link or creates a session. A reviewer who is not the account owner
approves or rejects the record with a note. A lost key is replaced only after approval.
"""

import frappe
from frappe import _

REVIEW_DOCTYPE = "PTR Recovery Review"
OPEN = "Open"
DECISIONS = ("Approved", "Rejected")
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


def check_decision(doc) -> None:
	previous = doc.get_doc_before_save()
	if previous is None:
		if doc.status != OPEN:
			frappe.throw(_("A recovery review starts open.", context="press_tr"), frappe.PermissionError)
		return
	if previous.status in DECISIONS:
		if doc.status != previous.status or (doc.review_note or "") != (previous.review_note or ""):
			frappe.throw(
				_("A recovery review decision is final.", context="press_tr"), frappe.PermissionError
			)
		return
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
