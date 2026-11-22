"""Event envelope and conversion from the Keycloak format.

This module is pure. It performs no network or disk operations.
The envelope contract is in `backend/contracts/identity_sync.openapi.yaml`.

The envelope contains no personal data. The service does not read fields such as email from events.
The service reads the current user state from Keycloak.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass

USER_TYPES = frozenset({"REGISTER", "VERIFY_EMAIL", "UPDATE_EMAIL", "DELETE_ACCOUNT"})
MEMBERSHIP_TYPES = frozenset({"ORGANIZATION_MEMBERSHIP_CREATE", "ORGANIZATION_MEMBERSHIP_DELETE"})
ADMIN_TYPES = frozenset({"USER_CREATE", "USER_UPDATE", "USER_DELETE"}) | MEMBERSHIP_TYPES
# A request the service records itself. It never arrives through the event endpoint:
# `parse_event` accepts only the kinds `user` and `admin`.
REQUEST_KIND = "request"
ACCOUNT_DELETION = "ACCOUNT_DELETION"
# Events that say Keycloak no longer has the user. Keycloak's own delete_account action is
# switched off, so in practice this is an administrator's delete (docs/sozlesmeler.md, section 7).
USER_REMOVED_TYPES = frozenset({"USER_DELETE", "DELETE_ACCOUNT"})
# The account job for a user that Keycloak no longer has: steps 2, 3 and 4 only.
ACCOUNT_REMOVAL = "ACCOUNT_REMOVAL"
# Both are the same job for one account. They differ only in the Keycloak steps.
JOB_TYPES = frozenset({ACCOUNT_DELETION, ACCOUNT_REMOVAL})

MAX_ID_LENGTH = 128
# IDs appear in URL paths, so only safe characters are accepted.
RESOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_FIELD_LENGTH = 255


class EventError(ValueError):
    """The event envelope does not match the contract."""


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    type: str
    realm: str
    time: int
    user_id: str | None = None
    organization_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def is_handled(event: Event) -> bool:
    """Whether the service handles this event."""
    if event.kind == "user":
        return event.type in USER_TYPES
    if event.kind == REQUEST_KIND:
        return event.type in JOB_TYPES
    return event.kind == "admin" and event.type in ADMIN_TYPES


def _text(payload: Mapping[str, object], name: str, *, required: bool, max_length: int = _MAX_FIELD_LENGTH) -> str | None:
    value = payload.get(name)
    if value is None:
        if required:
            raise EventError(f"missing field: {name}")
        return None
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise EventError(f"invalid field: {name}")
    return value


def _resource_id(payload: Mapping[str, object], name: str) -> str | None:
    value = _text(payload, name, required=False)
    if value is not None and not RESOURCE_ID.fullmatch(value):
        raise EventError(f"invalid field: {name}")
    return value


def parse_event(payload: object) -> Event:
    """Validate the envelope and build an `Event`. Discard unused fields."""
    if not isinstance(payload, Mapping):
        raise EventError("event must be an object")
    kind = _text(payload, "kind", required=True)
    if kind not in ("user", "admin"):
        raise EventError("invalid field: kind")
    time = payload.get("time")
    if isinstance(time, bool) or not isinstance(time, int):
        raise EventError("invalid field: time" if "time" in payload else "missing field: time")
    event = Event(
        id=_text(payload, "id", required=True, max_length=MAX_ID_LENGTH) or "",
        kind=kind,
        type=_text(payload, "type", required=True) or "",
        realm=_text(payload, "realm", required=True) or "",
        time=time,
        user_id=_resource_id(payload, "user_id"),
        organization_id=_resource_id(payload, "organization_id"),
    )
    if is_handled(event):
        if event.user_id is None:
            raise EventError("missing field: user_id")
        if event.type in MEMBERSHIP_TYPES and event.organization_id is None:
            raise EventError("missing field: organization_id")
    return event


def looks_like_keycloak(payload: object) -> bool:
    """Whether the body uses the native Keycloak event format."""
    return isinstance(payload, Mapping) and "kind" not in payload and "realmId" in payload


OTHER_REALM = "(other realm)"


def from_keycloak(payload: Mapping[str, object], *, realm_id: str, realm: str) -> dict[str, object]:
    """Convert a Keycloak event representation to the service envelope.

    User events contain `type` and `userId`. Admin events contain `operationType`,
    `resourceType`, and `resourcePath`. Source: Keycloak 26.8.2 Admin REST API.

    Keycloak writes the internal realm ID to `realmId`, not the realm name
    (EventBuilder.java, 26.8.2). `realm_id` is the trusted ID from configuration.
    If the event realm ID matches it, the envelope uses the `realm` name. Otherwise the event belongs to another realm.
    """
    if not isinstance(payload, Mapping) or "realmId" not in payload:
        raise EventError("not a Keycloak event")
    if not realm_id:
        raise EventError("realm id is not configured")
    same_realm = payload.get("realmId") == realm_id
    envelope: dict[str, object] = {"realm": realm if same_realm else OTHER_REALM, "time": payload.get("time")}
    if "operationType" in payload or "resourceType" in payload:
        resource = str(payload.get("resourceType") or "")
        operation = str(payload.get("operationType") or "")
        path = str(payload.get("resourcePath") or "")
        envelope["kind"] = "admin"
        envelope["type"] = f"{resource}_{operation}"
        parts = [part for part in path.split("/") if part]
        if resource == "USER" and len(parts) >= 2 and parts[0] == "users":
            envelope["user_id"] = parts[1]
        elif resource == "ORGANIZATION_MEMBERSHIP" and len(parts) >= 3 and parts[0] == "organizations":
            envelope["organization_id"] = parts[1]
            # Keycloak omits the user ID from the path in member-addition events.
            if len(parts) >= 4 and parts[2] == "members":
                envelope["user_id"] = parts[3]
        envelope["id"] = payload.get("id") or _derived_id(payload.get("time"), resource, operation, path)
    elif "type" in payload:
        envelope["kind"] = "user"
        envelope["type"] = payload.get("type")
        envelope["id"] = payload.get("id")
        if payload.get("userId") is not None:
            envelope["user_id"] = payload.get("userId")
    else:
        raise EventError("not a Keycloak event")
    return envelope


def _derived_id(*parts: object) -> str:
    joined = "\x1f".join(str(part) for part in parts)
    return "kc-" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:40]
