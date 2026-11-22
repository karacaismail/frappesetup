"""Wire validation and signed, scoped cursors for mobile contract version 1."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass


PAGE_SIZE = 100
BATCH_SIZE = 20
BODY_BYTES = 256 * 1024
REQUESTS_PER_MINUTE = 60
CURSOR_SECONDS = 7 * 86400
RETENTION_DAYS = 30
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


def content_digest(operation):
    return hashlib.sha256(_json_bytes(operation)).hexdigest()


def validate_operation(operation, commands):
    if not isinstance(operation, dict) or operation.keys() - {
        "operation_id", "command", "record_id", "version", "fields"
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


def _signature(secret, scope, body):
    return hmac.digest(secret, _json_bytes(["mobile-v1", *scope]) + b"." + body, "sha256").hex()


def encode_cursor(secret, scope, *, after, ceiling, now):
    payload = _json_bytes([after, ceiling, now + CURSOR_SECONDS])
    body = base64.urlsafe_b64encode(payload).rstrip(b"=")
    return f"{body.decode()}.{_signature(secret, scope, body)}"


def decode_cursor(secret, scope, token, *, now, floor):
    try:
        if not isinstance(token, str) or len(token) > 2048:
            raise ValueError
        raw_body, signature = token.split(".")
        body = raw_body.encode("ascii")
        if not hmac.compare_digest(signature, _signature(secret, scope, body)):
            raise ValueError
        payload = base64.b64decode(body + b"=" * (-len(body) % 4), altchars=b"-_", validate=True)
        after, ceiling, expires = json.loads(payload)
        if any(type(value) is not int for value in (after, ceiling, expires)):
            raise ValueError
        if not floor <= after <= ceiling or now >= expires:
            raise ValueError
    except (ValueError, TypeError, binascii.Error) as error:
        raise MobileError("invalid_cursor", 410) from error
    return after, ceiling
