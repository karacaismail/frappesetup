"""Account deletion on the tenant site: disable the user and anonymize the person (PROJE-KAYDI.md O-27).

Frappe 16 ships the anonymization engine: “Personal Data Deletion Request” applies the
`user_data_fields` hooks of every installed app, redacts the listed fields, keeps the records and finally
renames the user to `deleted-user-<n>@<site>`
(frappe/website/doctype/personal_data_deletion_request/personal_data_deletion_request.py:260).
This module reuses that engine and the hook, so each app keeps declaring its own person fields.

The request's own lifecycle is not used, for these reasons (same file):
- `after_insert` e-mails a confirmation link to the user (line 67). Consent already came through
  identity-sync, and a mail would put the address into “Email Queue” again.
- `trigger_data_deletion` needs a System Manager approval step and e-mails the old address (line 125).
- `anonymize_data` enqueues the work on the long queue (line 132). The caller needs a synchronous result
  to know that step 4 of the deletion flow is done.
- automatic processing runs from `scheduler_events` (frappe/hooks.py:282), which this project does not use.

So the record is written with `db_insert` (no `after_insert`) and `_anonymize_data` runs in the request.
`_anonymize_data` is the method `anonymize_data` enqueues; tests break if a Frappe upgrade changes it.
"""

import frappe
from frappe import _
from frappe.model.naming import set_new_name

from platform_core.kimlik import provisioning
from platform_core.kimlik.exceptions import IdentityConflict, IdentityNotFound

REQUEST = "Personal Data Deletion Request"
DELETED = "Deleted"
PROTECTED_USERS = ("Administrator", "Guest")


def anonymize_user(data: dict) -> dict:
	issuer = provisioning._issuer(data)
	subject = provisioning._text(data, "subject", provisioning.MAX_SUBJECT)
	# Locking reads: a retry that arrives while the first call is still open waits for its commit, then
	# sees the anonymous name and the finished request (review finding, repeatable request rule).
	user = frappe.db.get_value(
		provisioning.LINK, {"issuer": issuer, "subject": subject}, "user", for_update=True
	)
	if not user:
		frappe.throw(_("No user is linked to this identity."), IdentityNotFound)
	if user in PROTECTED_USERS:
		frappe.throw(_("This account cannot be anonymized."), IdentityConflict)
	if frappe.db.get_value(REQUEST, user, "status", for_update=True) == DELETED:
		# Repeated request: the link already points to the anonymous user.
		return _result(user)

	doc = frappe.get_doc("User", user)
	if doc.enabled:
		# User.on_update closes every session of a disabled user (frappe/core/doctype/user/user.py:362).
		doc.enabled = 0
		doc.save()

	request = frappe.new_doc(REQUEST)
	request.email = user
	request.status = "Pending Approval"
	set_new_name(request)
	# G-4: no `after_insert`, so no confirmation e-mail. The request runs as the administrator through
	# the identity-sync service token; the target comes from the verified identity link.
	request.db_insert()
	request._anonymize_data(email=user, anon=request.name, commit=False)
	# The engine keeps the original address in the request. Replace it with the anonymous name.
	request.db_set("email", request.name, update_modified=False)
	return _result(request.name)


def _result(user: str) -> dict:
	return {"user": user, "enabled": False, "status": DELETED}
