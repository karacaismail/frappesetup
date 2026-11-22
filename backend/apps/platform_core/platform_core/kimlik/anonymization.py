"""Account deletion on the tenant site (PROJE-KAYDI.md O-27, docs/sozlesmeler.md section 7, anonymization rules).

Two steps, both safe to repeat:

1. `disable_step` closes the account: the user is disabled, API keys and stored secrets are deleted,
   the deletion is recorded and committed. Then every session is closed page by page.
   Frappe commits once per closed session (frappe/sessions.py:96) and returns at most 100 sessions per
   query (frappe/sessions.py:76). Closing them after the commit keeps the record safe.
2. `anonymize_step` removes the personal data, renames the user to an anonymous name and deletes the
   identity link, so the raw `sub` is gone. No session is left, so no Frappe call commits early.

The deletion record keeps only the HMAC-SHA256 digest of `(iss, sub)` (`identity_hash`). Provisioning,
enabling and e-mail changes check it first and take the same row locks in the same order:
identity link first, deletion record second.

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

from platform_core.kimlik import anonymization_scope, provisioning
from platform_core.kimlik.exceptions import (
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
			_("The deletion key is not configured: {0}", context="platform_core.kimlik").format(KEY_SETTING),
			DeletionKeyMissing,
		)
	message = f"{issuer}\n{subject}".encode()
	return hmac.new(str(key).encode(), message, hashlib.sha256).hexdigest()


def lock_identity(issuer: str, subject: str) -> tuple[frappe._dict | None, frappe._dict | None]:
	"""Locks the identity link and then the deletion record of `(iss, sub)`. Same order everywhere."""
	link = frappe.db.get_value(
		provisioning.LINK,
		{"issuer": issuer, "subject": subject},
		["name", "user"],
		as_dict=True,
		for_update=True,
	)
	record = frappe.db.get_value(
		DELETION, identity_hash(issuer, subject), ["name", "state", "user"], as_dict=True, for_update=True
	)
	return link, record


def refuse_if_deleted(issuer: str, subject: str) -> frappe._dict | None:
	"""For provisioning, enabling and e-mail changes. Returns the locked link, or raises 410."""
	link, record = lock_identity(issuer, subject)
	if record:
		frappe.throw(
			_("This identity was deleted and cannot be used again.", context="platform_core.kimlik"),
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


def _with_retry(step, issuer: str, subject: str, attempts: int = 3):
	"""Runs a step in a fresh transaction. Retries when a parallel call changed the locked rows.

	MariaDB refuses a locking read of a row that changed after the transaction's snapshot
	(error 1020, `QueryDeadlockError` in Frappe). Starting a new transaction just before the lock and
	retrying makes the second of two parallel calls see the first call's committed result.
	"""
	for attempt in range(attempts):
		frappe.db.commit()
		try:
			return step(issuer, subject)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt == attempts - 1:
				raise


def disable_step(issuer: str, subject: str) -> frappe._dict:
	"""Step 1. Records the deletion and closes the account. Commits before any session is closed."""
	link, record = lock_identity(issuer, subject)
	if record:
		frappe.db.commit()
		return record
	if not link:
		frappe.throw(
			_("No user is linked to this identity.", context="platform_core.kimlik"), IdentityNotFound
		)
	if link.user in PROTECTED_USERS:
		frappe.throw(
			_("This account cannot be anonymized.", context="platform_core.kimlik"), IdentityConflict
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
	doc.insert(ignore_permissions=True)
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
			_("No user is linked to this identity.", context="platform_core.kimlik"), IdentityNotFound
		)
	if record.state == ANONYMIZED:
		return _result(record.user)
	user = record.user
	anon = _anonymous_name(record.name)
	anonymization_scope.anonymize(user, anon)
	if frappe.db.exists("User", user) and user != anon:
		rename_doc("User", user, anon, force=True, show_alert=False)
	if link:
		frappe.db.delete(provisioning.LINK, {"name": link.name})
	frappe.db.set_value(DELETION, record.name, {"state": ANONYMIZED, "user": anon}, update_modified=False)
	return _result(anon)


def _anonymous_name(record_name: str) -> str:
	# Derived from the record, so a retry chooses the same name. The record name is a keyed digest.
	return f"deleted-user-{record_name[:16]}@{ANON_DOMAIN}"


def _result(user: str) -> dict:
	return {"user": user, "enabled": False, "status": ANONYMIZED}
