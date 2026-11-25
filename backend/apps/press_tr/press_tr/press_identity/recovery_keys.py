"""Remove the old keys after an approved recovery (AJA-420, design in AJA-426).

A reviewer approved a `PTR Recovery Review` record. A person with write permission on the
record, who is not the account owner, then starts this step. Press asks identity-sync to
remove the user's strong keys set up before the approval. identity-sync alone calls Keycloak.

The step is repeatable. A Completed record does not call the service again. A failed call
leaves the record in Removal Failed with a short error code, so the step can run again.
The record's change history is the audit trail: Frappe records who changed the state and when.
"""

from zoneinfo import ZoneInfo

import frappe
from frappe import _

from press_tr.press_identity.deletion import KeyRemovalFailed, browser_session, send_key_removal_request
from press_tr.press_identity.recovery import (
	APPROVED,
	COMPLETED,
	REMOVAL_FAILED,
	REVIEW_DOCTYPE,
)


def _refuse(message: str) -> None:
	frappe.throw(message, frappe.PermissionError)


def approved_at_seconds(reviewed_at) -> int:
	# Frappe stores the time in the system time zone without the zone. Keycloak counts in UTC.
	moment = frappe.utils.get_datetime(reviewed_at)
	zone = ZoneInfo(frappe.utils.get_system_timezone())
	# Round down, so a key set up in the same second as the approval is never removed.
	return int(moment.replace(tzinfo=zone).timestamp())


def remove_recovered_keys(review: str) -> dict[str, str]:
	browser_session()
	if not isinstance(review, str) or not review:
		_refuse(_("Choose a recovery review.", context="press_tr"))
	# The document type check comes first, so a person without the role learns nothing about names.
	if not frappe.has_permission(REVIEW_DOCTYPE, "write") or not frappe.has_permission(
		REVIEW_DOCTYPE, "write", review
	):
		_refuse(_("You cannot remove keys for this recovery review.", context="press_tr"))
	# The lock keeps two calls for the same record from reaching the service together.
	doc = frappe.get_doc(REVIEW_DOCTYPE, review, for_update=True)
	owner = frappe.db.get_value("PTR Identity Link", doc.identity_link, "user")
	if frappe.session.user in ("Guest", owner):
		_refuse(_("The account owner cannot remove keys for their own recovery request.", context="press_tr"))
	if doc.status == COMPLETED:
		return {"status": COMPLETED}
	if doc.status not in (APPROVED, REMOVAL_FAILED):
		_refuse(_("Keys are removed only after a recovery review is approved.", context="press_tr"))

	link = frappe.db.get_value(
		"PTR Identity Link", doc.identity_link, ["issuer", "subject"], as_dict=True
	)
	now = frappe.utils.now_datetime()
	try:
		send_key_removal_request(link, doc.name, approved_at_seconds(doc.reviewed_at))
		error = None
	except KeyRemovalFailed as failure:
		error = failure.code

	doc.flags.key_removal = True
	doc.removal_attempted_at = now
	doc.removal_error = error
	if error:
		doc.status = REMOVAL_FAILED
	else:
		doc.status = COMPLETED
		doc.completed_at = now
	# The record is saved on failure too, so the error stays visible and the history shows the attempt.
	doc.save()
	return {"status": doc.status, "error": error} if error else {"status": doc.status}
