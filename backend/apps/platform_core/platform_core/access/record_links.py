"""Private links are locators. The session user's existing permissions still apply."""

import json
import re
import secrets
from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import frappe
from frappe.database.database import savepoint
from frappe.utils import now_datetime

LINK = "PLT Record Link"
REQUEST = "PLT Record Access Request"
LIFETIME = timedelta(days=7)
TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")
ID_SHAPE = re.compile(r"[a-f0-9]{32}")


def _reply(status_code, **payload):
	frappe.local.response_headers.update(
		{
			"Cache-Control": "private, no-store",
			"Referrer-Policy": "no-referrer",
			"Vary": "Cookie, Authorization",
			"X-Robots-Tag": "noindex, nofollow",
		}
	)
	frappe.response["http_status_code"] = status_code
	return payload


@contextmanager
def _without_messages():
	previous = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		yield
	finally:
		frappe.flags.mute_messages = previous


def _target(doctype, name):
	if not doctype or not name or max(len(doctype), len(name)) > 140:
		return None
	with _without_messages():
		try:
			meta = frappe.get_meta(doctype)
			if meta.istable or meta.issingle or meta.is_virtual or doctype in {LINK, REQUEST}:
				return None
			return frappe.get_doc(doctype, name)
		except frappe.DoesNotExistError:
			return None


def _allowed(doc, ptype, user):
	# Frappe adds a denial message to the response. The message would show that the record exists.
	with _without_messages():
		return bool(doc) and doc.has_permission(ptype, user=user)


def _can_share(doc, user):
	return _allowed(doc, "read", user) and _allowed(doc, "share", user)


def _audit(event, reference_type, reference_name, user):
	# The event contains only the internal link or request ID.
	frappe.get_doc(
		doctype="Activity Log",
		name=uuid4().hex,
		reference_doctype=reference_type,
		reference_name=reference_name,
		subject=event,
		status="Success",
		user=user,
		communication_date=now_datetime(),
	).db_insert()


def create(doctype, name):
	user = frappe.session.user
	target = _target(doctype, name)
	if not _can_share(target, user):
		return _reply(404, status="unavailable")
	token = secrets.token_urlsafe(32)
	link_id = uuid4().hex
	# The target's read and share checks authorize this internal row.
	frappe.get_doc(
		doctype=LINK,
		name=link_id,
		token_hash=sha256(token.encode("ascii")).hexdigest(),
		target_type=target.doctype,
		target_name=target.name,
		expires_at=now_datetime() + LIFETIME,
	).db_insert()
	_audit("Record link created", LINK, link_id, user)
	return _reply(200, id=link_id, path=f"/panel/share#{token}")


def _by_token(token, *, lock=False):
	if not TOKEN_SHAPE.fullmatch(token):
		return None
	# The token finds an internal row. The caller checks record permissions before exposing the target.
	return frappe.db.get_value(
		LINK,
		{"token_hash": sha256(token.encode("ascii")).hexdigest()},
		["name", "target_type", "target_name", "expires_at", "revoked_at"],
		as_dict=True,
		for_update=lock,
	)


def _gone(link):
	return link.revoked_at or link.expires_at <= now_datetime()


def open_link(token):
	link = _by_token(token)
	if link:
		if _gone(link):
			return _reply(410, status="gone")
		target = _target(link.target_type, link.target_name)
		if _allowed(target, "read", frappe.session.user):
			return _reply(200, doctype=target.doctype, name=target.name)
	return _reply(404, status="unavailable")


def revoke(link_id):
	if not ID_SHAPE.fullmatch(link_id):
		return _reply(404, status="unavailable")
	user = frappe.session.user
	# This internal lookup is locked. Revocation is restricted below to the creator or a current sharer.
	link = frappe.db.get_value(
		LINK, link_id, ["owner", "target_type", "target_name", "revoked_at"], as_dict=True, for_update=True
	)
	if not link or (link.owner != user and not _can_share(_target(link.target_type, link.target_name), user)):
		return _reply(404, status="unavailable")
	if not link.revoked_at:
		# Only the creator or a current sharer can revoke. The row stays locked through the audit insert.
		frappe.db.set_value(LINK, link_id, "revoked_at", now_datetime())
		_audit("Record link revoked", LINK, link_id, user)
	return _reply(200, status="revoked")


def request_access(token, doctype, name):
	user = frappe.session.user
	link = None
	if token is not None:
		link = _by_token(token, lock=True)
		if not link or _gone(link):
			return _reply(202, status="received")
		doctype, name = link.target_type, link.target_name
	target = _target(doctype, name)
	if target and not _allowed(target, "read", user):
		key = json.dumps([user, target.doctype, target.name])
		request_id = sha256(key.encode("utf-8")).hexdigest()
		# The primary key deduplicates this requester and target atomically across links.
		with _without_messages(), savepoint(catch=frappe.DuplicateEntryError):
			frappe.get_doc(
				doctype=REQUEST,
				name=request_id,
				record_link=link.name if link else None,
				target_type=target.doctype,
				target_name=target.name,
			).db_insert()
			_audit("Record access requested", REQUEST, request_id, user)
	return _reply(202, status="received")
