"""Account deletion on the tenant site (PROJE-KAYDI.md O-27, docs/sozlesmeler.md section 7, anonymization rules).

Two steps, both safe to repeat:

1. `disable_step` closes the account: the user is disabled, API keys and stored secrets are deleted,
   the deletion is recorded and committed. Then every session is closed page by page.
   Frappe commits once per closed session (frappe/sessions.py:96) and returns at most 100 sessions per
   query (frappe/sessions.py:76). Closing them after the commit keeps the record safe.
2. `anonymize_step` removes the personal data, renames the user to an anonymous name and deletes the
   identity link, so the raw `sub` is gone. No session is left, so no Frappe call commits early.

The deletion record keeps only the HMAC-SHA256 digest of `(iss, sub)` (`identity_hash`). Provisioning,
enabling and e-mail changes check it before altering data. All paths use the same lock order:
existing User first, then the identity link and the deletion record.

Frappe's “Personal Data Deletion Request” is not used. Its engine replaces the full name in every row of
some tables (personal_data_deletion_request.py:317), which could change another person's text.
`kimlik.anonymization_scope` changes only rows bound to the user.
"""

import hashlib
import hmac

import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc
from frappe.sessions import delete_session, get_sessions_to_clear
from frappe.utils import now_datetime
from frappe.utils.password import delete_all_passwords_for

from platform_core.identity import anonymization_scope, provisioning
from platform_core.identity.exceptions import (
	DeletionKeyMissing,
	IdentityConflict,
	IdentityDeleted,
	IdentityNotFound,
)

DELETION = "Platform Identity Deletion"
DISABLED = "Disabled"
ANONYMIZED = "Anonymized"
PROTECTED_USERS = ("Administrator", "Guest")
KEY_SETTING = "kimlik_deletion_hmac_key"
ANON_DOMAIN = "deleted.invalid"


def identity_hash(issuer: str, subject: str) -> str:
	key = frappe.conf.get(KEY_SETTING)
	if not key:
		frappe.throw(
			_("The deletion key is not configured: {0}", context="platform_core.identity").format(
				KEY_SETTING
			),
			DeletionKeyMissing,
		)
	message = f"{issuer}\n{subject}".encode()
	return hmac.new(str(key).encode(), message, hashlib.sha256).hexdigest()


def lock_identity(
	issuer: str, subject: str, *, require_key: bool = True, candidate_user: str | None = None
) -> tuple[frappe._dict | None, frappe._dict | None]:
	"""Locks the existing User, then the identity link, then the deletion record.

	Frappe renames the User before updating its link fields. Follow the same order.

	Sign-in may skip the deletion record if the deletion key is missing.
	Identity changes still fail with 503 when the key is missing.
	"""
	filters = {"issuer": issuer, "subject": subject}
	linked_user = frappe.db.get_value(provisioning.LINK, filters, "user")
	user = linked_user or candidate_user
	locked_user = None
	if user and (linked_user or frappe.db.exists("User", user)):
		locked_user = frappe.db.get_value("User", user, "name", for_update=True)
	link = frappe.db.get_value(provisioning.LINK, filters, ["name", "user"], as_dict=True, for_update=True)
	if link and link.user != locked_user:
		# The optimistic lookup is only for lock ordering. Do not use a different link under this lock.
		raise frappe.QueryDeadlockError("Identity link changed while acquiring locks")
	if not require_key and not frappe.conf.get(KEY_SETTING):
		return link, None
	record = frappe.db.get_value(
		DELETION, identity_hash(issuer, subject), ["name", "state", "user"], as_dict=True, for_update=True
	)
	return link, record


def refuse_if_deleted(issuer: str, subject: str, *, candidate_user: str | None = None) -> frappe._dict | None:
	"""For provisioning, enabling and e-mail changes. Returns the locked link, or raises 410."""
	link, record = _lock_identity_with_retry(issuer, subject, candidate_user=candidate_user)
	if record:
		frappe.throw(
			_("This identity was deleted and cannot be used again.", context="platform_core.identity"),
			IdentityDeleted,
		)
	return link


def is_deleted(issuer: str, subject: str) -> bool:
	"""Read-only check for the sign-in path. A missing key never blocks sign-in."""
	if not frappe.conf.get(KEY_SETTING):
		return False
	return bool(frappe.db.exists(DELETION, identity_hash(issuer, subject)))


def anonymize_user(data: dict) -> dict:
	issuer = provisioning._issuer(data)
	subject = provisioning._text(data, "subject", provisioning.MAX_SUBJECT)
	record = _with_retry(disable_step, issuer, subject)
	if record.state == ANONYMIZED:
		return _result(record.user)
	close_sessions(record.user)
	return _with_retry(anonymize_step, issuer, subject)


def _with_retry(step, issuer: str, subject: str):
	"""Run each repeatable deletion step in a fresh transaction.

	MariaDB can refuse a locking read if a row changed after the transaction's snapshot
	(error 1020, exposed as QueryDeadlockError by Frappe). Starting a fresh transaction
	before the step lets the next attempt see the other call's committed changes.
	"""
	for attempt in range(3):
		frappe.db.commit()
		try:
			return step(issuer, subject)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt == 2:
				raise


def _lock_identity_with_retry(
	issuer: str, subject: str, *, candidate_user: str | None = None, require_key: bool = True
) -> tuple[frappe._dict | None, frappe._dict | None]:
	"""Retry a changed snapshot before any write or irreversible side effect."""
	for attempt in range(3):
		try:
			return lock_identity(issuer, subject, candidate_user=candidate_user, require_key=require_key)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt == 2:
				raise


def disable_step(issuer: str, subject: str) -> frappe._dict:
	"""Step 1. Records the deletion and closes the account. Commits before any session is closed."""
	link, record = lock_identity(issuer, subject)
	if record:
		frappe.db.commit()
		return record
	if not link:
		frappe.throw(
			_("No user is linked to this identity.", context="platform_core.identity"), IdentityNotFound
		)
	if link.user in PROTECTED_USERS:
		frappe.throw(
			_("This account cannot be anonymized.", context="platform_core.identity"), IdentityConflict
		)
	doc = frappe.new_doc(DELETION)
	doc.update(
		{
			"identity_hash": identity_hash(issuer, subject),
			"state": DISABLED,
			"user": link.user,
			"deleted_at": now_datetime(),
		}
	)
	# G-4: the request runs as the administrator through the identity-sync service token; the target
	# comes from the verified identity link, not from client input.
	doc.insert()
	_close_account(link.user)
	frappe.db.commit()
	return frappe._dict(name=doc.name, state=DISABLED, user=link.user)


def _close_account(user: str) -> None:
	# V-1 exception: direct writes avoid `User.on_update`, which closes sessions and commits midway
	# (frappe/sessions.py:96). Sessions are closed after the commit by `close_sessions`.
	frappe.db.set_value("User", user, {"enabled": 0, "api_key": None}, update_modified=False)
	# Deletes the API secret and the password (table `__Auth`, frappe/utils/password.py:163).
	delete_all_passwords_for("User", user)
	frappe.cache.delete_key("enabled_users")
	frappe.cache.delete_key("users_for_mentions")
	frappe.cache.hdel("user_doc", user)


def close_sessions(user: str) -> None:
	"""Closes every session page by page. Frappe returns at most 100 per query (frappe/sessions.py:76)."""
	while sids := get_sessions_to_clear(user=user, force=True):
		for sid in sids:
			delete_session(sid, user=user, reason="Account deleted")


def anonymize_step(issuer: str, subject: str) -> dict:
	"""Step 2. Removes personal data, renames the user and deletes the identity link (raw `sub`)."""
	link, record = lock_identity(issuer, subject)
	if not record:
		frappe.throw(
			_("No user is linked to this identity.", context="platform_core.identity"), IdentityNotFound
		)
	if record.state == ANONYMIZED:
		return _result(record.user)
	user = record.user
	anon = _anonymous_name(record.name)
	anonymization_scope.anonymize(user, anon)
	if frappe.db.exists("User", user) and user != anon:
		rename_doc("User", user, anon, force=True, show_alert=False)
		# The Frappe rename writes an Edit comment that names the old address.
		anonymization_scope.scrub_after_rename(user, anon)
	if link:
		_forget_link(link.name)
	frappe.db.set_value(DELETION, record.name, {"state": ANONYMIZED, "user": anon}, update_modified=False)
	return _result(anon)


def _forget_link(name: str) -> None:
	"""Deletes the identity link and its history, so the raw `sub` is gone (G-15, contract rule 2).

	V-1 exception: `frappe.delete_doc` would keep a full copy in “Deleted Document”, raw `sub` included.
	The link has no controller hooks that must run on deletion, so a direct delete is used. The link tracks
	changes, so its Version rows and comments are deleted too.
	"""
	frappe.db.delete("Version", {"ref_doctype": provisioning.LINK, "docname": name})
	frappe.db.delete("Comment", {"reference_doctype": provisioning.LINK, "reference_name": name})
	frappe.db.delete(provisioning.LINK, {"name": name})


def _anonymous_name(record_name: str) -> str:
	# Derived from the record, so a retry chooses the same name. The record name is a keyed digest.
	return f"deleted-user-{record_name[:16]}@{ANON_DOMAIN}"


def _result(user: str) -> dict:
	return {"user": user, "enabled": False, "status": ANONYMIZED}
