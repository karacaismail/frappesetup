"""Olay zarfı ve Keycloak biçiminden çeviri.

Bu modül saftır. Ağa ve diske dokunmaz.
Zarfın sözleşmesi `backend/contracts/identity_sync.openapi.yaml` dosyasındadır.

Zarf kişisel veri taşımaz. Servis e-posta gibi alanları olaydan almaz.
Servis kullanıcının güncel durumunu Keycloak'tan okur.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass

USER_TYPES = frozenset({"REGISTER", "VERIFY_EMAIL", "UPDATE_EMAIL", "DELETE_ACCOUNT"})
MEMBERSHIP_TYPES = frozenset({"ORGANIZATION_MEMBERSHIP_CREATE", "ORGANIZATION_MEMBERSHIP_DELETE"})
ADMIN_TYPES = frozenset({"USER_CREATE", "USER_UPDATE", "USER_DELETE"}) | MEMBERSHIP_TYPES

MAX_ID_LENGTH = 128
_MAX_FIELD_LENGTH = 255


class EventError(ValueError):
    """Olay zarfı sözleşmeye uymuyor."""


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
    """Servis bu olay için iş yapar mı?"""
    if event.kind == "user":
        return event.type in USER_TYPES
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


def parse_event(payload: object) -> Event:
    """Zarfı doğrular ve `Event` üretir. Gereksiz alanları atar."""
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
        user_id=_text(payload, "user_id", required=False),
        organization_id=_text(payload, "organization_id", required=False),
    )
    if is_handled(event):
        if event.user_id is None:
            raise EventError("missing field: user_id")
        if event.type in MEMBERSHIP_TYPES and event.organization_id is None:
            raise EventError("missing field: organization_id")
    return event


def looks_like_keycloak(payload: object) -> bool:
    """Gövde Keycloak'ın kendi olay biçiminde mi?"""
    return isinstance(payload, Mapping) and "kind" not in payload and "realmId" in payload


def from_keycloak(payload: Mapping[str, object]) -> dict[str, object]:
    """Keycloak'ın olay gösterimini servis zarfına çevirir.

    Kullanıcı olayı `type` ve `userId` taşır. Yönetici olayı `operationType`,
    `resourceType` ve `resourcePath` taşır. Kaynak: Keycloak 26.8.2 Admin REST API.
    """
    if not isinstance(payload, Mapping) or "realmId" not in payload:
        raise EventError("not a Keycloak event")
    envelope: dict[str, object] = {"realm": payload.get("realmId"), "time": payload.get("time")}
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
            # Keycloak üye ekleme olayında yola kullanıcı kimliğini yazmaz.
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
