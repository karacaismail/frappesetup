"""Frappe link of the AtonotA Login verification inbox (G-164, AJA-231).

The rules live in the `atonota_login` package (`atonota_login.verification_inbox`). That package has no
Frappe code. This module is the thin Frappe layer around it:

1. `receive_notice` checks the signature over the raw request body and stores one notice.
   It never reads `frappe.form_dict`. It empties it, so body fields cannot reach a log.
2. `process` does not run in the request. The request hands it to `frappe.enqueue`.
3. `FrappeNoticeStore` keeps the notices in `PLT Verification Notice` and the cases in
   `PLT Verification Case`. The provider's event id is unique in the database.

No scheduled job runs here. `replay_unknown` runs by hand only, for the System Manager role:
`bench --site <site> execute platform_core.identity.atonota.verification_api.replay_unknown`.
The provider is not chosen yet. Until the `atonota_verification_secret` site setting exists, every
notice gets `VerificationNotConfigured` (503). The generic HMAC adapter of the package checks it.
Contract: `backend/contracts/platform_core-identity.openapi.yaml`, tag `atonota-login`.
"""

import time
from contextlib import contextmanager

import frappe
from atonota_login import verification_inbox as inbox
from frappe import _

from platform_core.identity.exceptions import InvalidInput

NOTICE = "PLT Verification Notice"
CASE = "PLT Verification Case"
SIGNATURE_HEADER = inbox.SIGNATURE_HEADER
PROCESS_JOB = "platform_core.identity.atonota.verification_api.process_notices"
# Same limit as the Keycloak back-channel logout endpoint (G-7). It is not a provider figure.
RATE_LIMIT = 300
RATE_WINDOW_SECONDS = 60


class VerificationNotConfigured(frappe.ValidationError):
	"""No verification provider is configured. Nothing is stored."""

	http_status_code = 503


class NoticeSignatureRejected(frappe.AuthenticationError):
	"""The notice signature is missing, wrong or too old. Nothing is stored."""

	http_status_code = 401


class FrappeNoticeStore:
	"""`atonota_login.verification_inbox.NoticeStore` on two DocTypes.

	With `commit=False` a transaction only takes row locks; the request commits at its end.
	The queue job uses `commit=True`, so each processed notice is committed on its own.
	"""

	def __init__(self, commit: bool = False):
		self._commit = commit

	def close(self) -> None:
		pass

	@contextmanager
	def transaction(self):
		if not self._commit:
			yield
			return
		try:
			yield
		except BaseException:
			frappe.db.rollback()
			raise
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def _case(self, case_id: str, fields: list) -> dict | None:
		return frappe.db.get_value(CASE, {"case_id": case_id}, ["name", *fields], as_dict=True, for_update=True)

	def latest_attempt(self, case_id: str) -> int:
		row = self._case(case_id, ["latest_attempt"])
		return row.latest_attempt if row else 0

	def add_attempt(self, case_id: str, attempt: int) -> None:
		row = self._case(case_id, [])
		if row:
			frappe.db.set_value(CASE, row.name, "latest_attempt", attempt)
			return
		frappe.get_doc({"doctype": CASE, "case_id": case_id, "latest_attempt": attempt}).insert(
			ignore_permissions=True
		)

	def add_notice(self, event_id: str, case_id: str, attempt: int, outcome: str) -> bool:
		if frappe.db.exists(NOTICE, {"event_id": event_id}):
			return False
		doc = frappe.get_doc(
			{
				"doctype": NOTICE,
				"event_id": event_id,
				"case_id": case_id,
				"attempt": attempt,
				"outcome": outcome,
				"state": "pending",
			}
		)
		# Another request may store the same event between the check and the insert.
		# The unique index refuses the second insert; the savepoint keeps the rest of the request.
		frappe.db.savepoint("atonota_notice")
		try:
			doc.insert(ignore_permissions=True)
		except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
			frappe.db.rollback(save_point="atonota_notice")
			frappe.clear_last_message()
			return False
		return True

	def next_pending(self):
		table = frappe.qb.DocType(NOTICE)
		rows = (
			frappe.qb.from_(table)
			.select(table.name, table.event_id, table.case_id, table.attempt, table.outcome)
			.where(table.state == "pending")
			.orderby(table.creation)
			.orderby(table.name)
			.limit(1)
			.for_update()
			.run()
		)
		return tuple(rows[0]) if rows else None

	def set_state(self, key, state: str) -> None:
		frappe.db.set_value(NOTICE, key, "state", state)

	def current_decision(self, case_id: str):
		row = self._case(case_id, ["decided_attempt", "outcome"])
		if not row or not row.decided_attempt:
			return None
		return row.decided_attempt, row.outcome

	def set_decision(self, case_id: str, attempt: int, outcome: str) -> None:
		row = self._case(case_id, [])
		# The rules apply a decision only to a known attempt, so the case record exists.
		frappe.db.set_value(CASE, row.name, {"decided_attempt": attempt, "outcome": outcome})

	def requeue_unknown(self) -> int:
		table = frappe.qb.DocType(NOTICE)
		rows = frappe.qb.from_(table).select(table.name).where(table.state == "unknown-attempt").for_update().run()
		for (name,) in rows:
			frappe.db.set_value(NOTICE, name, "state", "pending")
		return len(rows)


def _verifier():
	# The secret lives in site_config.json only. It never goes into the repository.
	secret = frappe.conf.get("atonota_verification_secret")
	if not isinstance(secret, str) or not secret:
		return None
	try:
		return inbox.HmacSignature(secret.encode("utf-8"))
	except ValueError:
		# A secret shorter than 32 bytes is treated as no provider at all.
		return None


def _inbox(commit: bool = False) -> inbox.VerificationInbox:
	return inbox.VerificationInbox(FrappeNoticeStore(commit=commit), _verifier())


def receive_notice() -> dict:
	"""Checks and stores one provider notice. Called by `platform_core.api.atonota_login.verification_notice`."""
	raw_body = frappe.request.get_data(cache=True)
	# Frappe copies JSON body fields into form_dict before the endpoint runs, and its error log
	# writes form_dict. The body may carry document or face data, so form_dict is emptied first.
	frappe.local.form_dict = frappe._dict()
	headers = {SIGNATURE_HEADER: frappe.get_request_header(SIGNATURE_HEADER) or ""}
	try:
		status = _inbox().receive(raw_body, headers, int(time.time()))
	except inbox.ConfigurationRequired:
		frappe.throw(_("No verification provider is configured."), VerificationNotConfigured)
	except inbox.SignatureRejected:
		frappe.throw(_("The notice signature is not valid."), NoticeSignatureRejected)
	except ValueError as error:
		frappe.throw(str(error), InvalidInput)
	if status == "accepted":
		# The job starts after the notice is committed. It never runs inside this request.
		frappe.enqueue(PROCESS_JOB, queue="short", enqueue_after_commit=True)
	return {"status": status}


def process_notices() -> list:
	"""Applies every pending notice once. Runs in the queue worker, started by a stored notice."""
	return _inbox(commit=True).process()


def replay_unknown() -> int:
	"""Puts notices for unknown attempts back in the queue. A System Manager runs it by hand."""
	frappe.only_for("System Manager")
	count = _inbox(commit=True).replay_unknown()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	if count:
		frappe.enqueue(PROCESS_JOB, queue="short")
	return count


def open_attempt(case_id: str) -> int:
	"""Starts a new attempt of a case. The caller commits. Without a provider: `ConfigurationRequired`."""
	return _inbox().open_attempt(case_id)


def decision(case_id: str) -> str:
	"""The outcome of the newest attempt of a case, or "pending"."""
	return _inbox().decision(case_id)
