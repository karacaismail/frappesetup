"""Wire validation and encrypted, scoped cursors for mobile contract version 1."""

import base64
import binascii
import hashlib
import json
import os
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PAGE_SIZE = 100
BATCH_SIZE = 20
BODY_BYTES = 256 * 1024
REQUESTS_PER_MINUTE = 60
TOKEN_CLOCK_SKEW_SECONDS = 30
CURSOR_SECONDS = 7 * 86400
DELIVERY_AUDIT_SIZE = 100
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


class MobileError(Exception):
	def __init__(self, code, status=400, *, current=None):
		super().__init__(code)
		self.code = code
		self.status = status
		self.current = current


@dataclass(frozen=True)
class Command:
	action: str
	fields: frozenset[str]


def uuid4_id(value):
	if not isinstance(value, str) or not UUID_PATTERN.fullmatch(value):
		raise MobileError("invalid_uuid")
	return value


def _json_bytes(value):
	try:
		return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
	except (ValueError, TypeError, RecursionError) as error:
		raise MobileError("invalid_json") from error


def operation_key(site, account, operation_id):
	return content_digest([site, account, uuid4_id(operation_id)])


def scoped_record_key(record_type, principal, record_id):
	"""Derive an internal index key for a phone-assigned UUID."""
	return content_digest(["mobile-record-v1", record_type, principal, uuid4_id(record_id)])


def unavailable_record():
	return MobileError("record_not_found", 404)


def content_digest(operation):
	return hashlib.sha256(_json_bytes(operation)).hexdigest()


def validate_operation(operation, commands):
	if not isinstance(operation, dict) or operation.keys() - {
		"operation_id",
		"command",
		"record_id",
		"version",
		"fields",
	}:
		raise MobileError("invalid_operation")
	uuid4_id(operation.get("operation_id"))
	uuid4_id(operation.get("record_id"))

	name = operation.get("command")
	if not isinstance(name, str) or not 1 <= len(name) <= 80:
		raise MobileError("invalid_command")
	command = commands.get(name)
	if command is None:
		raise MobileError("unknown_command")

	fields = operation.get("fields", {})
	if not isinstance(fields, dict) or fields.keys() - command.fields:
		raise MobileError("invalid_fields")

	if command.action in {"update", "delete"}:
		version = operation.get("version")
		if not isinstance(version, str) or not 1 <= len(version) <= 128:
			raise MobileError("version_required")
	elif "version" in operation:
		raise MobileError("unexpected_version")
	return command


def check_version(expected, current):
	if current["version"] != expected:
		raise MobileError("version_conflict", 409, current=current)


def _cursor_context(scope):
	return _json_bytes(["mobile-v1", *scope])


def encode_cursor(
	secret, scope, *, after, ceiling, now, snapshot=False, delivery_after=None, snapshot_after=None
):
	payload = _json_bytes([after, ceiling, now + CURSOR_SECONDS, snapshot, delivery_after, snapshot_after])
	nonce = os.urandom(12)
	ciphertext = AESGCM(secret).encrypt(nonce, payload, _cursor_context(scope))
	return "e1." + base64.urlsafe_b64encode(nonce + ciphertext).rstrip(b"=").decode()


def decode_cursor(secret, scope, token, *, now, floor):
	try:
		if not isinstance(token, str) or len(token) > 2048:
			raise ValueError
		version, encoded = token.split(".")
		if version != "e1":
			raise ValueError
		raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
		if base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != encoded:
			raise ValueError
		payload = AESGCM(secret).decrypt(raw[:12], raw[12:], _cursor_context(scope))
		after, ceiling, expires, snapshot, delivery_after, snapshot_after = json.loads(payload)
		if any(type(value) is not int for value in (after, ceiling, expires)):
			raise ValueError
		if delivery_after is not None and (
			not isinstance(delivery_after, str) or re.fullmatch(r"[0-9a-f]{64}", delivery_after) is None
		):
			raise ValueError
		if snapshot_after is not None and (
			not snapshot
			or not isinstance(snapshot_after, list)
			or len(snapshot_after) != 2
			or not all(isinstance(value, str) for value in snapshot_after)
		):
			raise ValueError
		if type(snapshot) is not bool or not (0 if snapshot else floor) <= after <= ceiling or now >= expires:
			raise ValueError
	except (ValueError, TypeError, binascii.Error, InvalidTag) as error:
		raise MobileError("invalid_cursor", 410) from error
	return after, ceiling, snapshot, delivery_after, snapshot_after
