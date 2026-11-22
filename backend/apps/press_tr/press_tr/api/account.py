import secrets
import time

import frappe
from frappe import _

from press_tr.api.auth import start_login
from press_tr.press_identity.deletion import (
	clear_reauthentication,
	fresh_reauthentication,
	human_identity,
	mark_deletion_status,
	send_deletion_request,
)
from press_tr.press_identity.oidc import reject


@frappe.whitelist(methods=["POST"])
def request_deletion(confirm: bool = False) -> dict[str, str | bool]:
	link = human_identity()
	csrf_token = frappe.get_request_header("X-Frappe-CSRF-Token", "")
	saved_token = frappe.session.data.get("csrf_token")
	if not csrf_token or not saved_token or not secrets.compare_digest(csrf_token, saved_token):
		reject()
	if type(frappe.form_dict.get("confirm")) is not bool or set(frappe.form_dict) - {"cmd", "confirm"}:
		reject()
	if not confirm:
		return start_login(
			{"sid": frappe.session.sid, "subject": link.subject, "started_at": int(time.time())}
		)

	authenticated_at = fresh_reauthentication()
	if authenticated_at is None:
		frappe.throw(
			_("Verify your identity again before deleting your account.", context="press_tr"),
			frappe.PermissionError,
		)
	if not send_deletion_request(link, authenticated_at):
		mark_deletion_status("pending")
		return {"pending": True}
	mark_deletion_status("submitted")
	clear_reauthentication()
	return {"submitted": True}
