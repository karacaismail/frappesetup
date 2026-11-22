"""Olayı işleyen akış.

Sıra şudur: kullanıcının güncel durumunu oku, eylemleri planla, eylemleri çalıştır.
Başarısız olay bekleme kuyruğuna girer. Kuyruk yalnız elle yeniden işlenir.
Bu modülde zamanlanmış iş ve yoklama döngüsü yoktur (Proje kaydı D-6).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from identity_sync.events import MEMBERSHIP_TYPES, Event, is_handled
from identity_sync.httpjson import HttpError, TransportError
from identity_sync.keycloak_admin import KeycloakAdmin
from identity_sync.mapping import (
    Action,
    EnsureOrganization,
    PressEnsureTeam,
    PressRemoveTeamMember,
    Preview,
    Tenant,
    TenantChangeEmail,
    TenantProvision,
    TenantSetEnabled,
    plan_actions,
)
from identity_sync.sites import PressClient, TenantClient
from identity_sync.store import Store

T = TypeVar("T")

# Organization açıldıktan sonra durum bir kez daha okunur ve plan yenilenir.
_MAX_PASSES = 2
_BACKOFF_SECONDS = 0.2


@dataclass(frozen=True)
class EventResult:
    """`status` değerleri: processed, duplicate, ignored, dead_lettered, preview, failed."""

    status: str
    actions: tuple[str, ...] = ()
    previews: tuple[Preview, ...] = ()

    def to_dict(self) -> dict[str, object]:
        body: dict[str, object] = {"status": self.status, "actions": list(self.actions)}
        if self.status == "preview":
            body["previews"] = [preview.to_dict() for preview in self.previews]
        return body


class _Failed(Exception):
    """Bir adım kalıcı olarak başarısız oldu. Metin kişisel veri taşımaz."""


class Processor:
    def __init__(
        self,
        *,
        issuer: str,
        realm: str,
        tenants: Sequence[Tenant],
        keycloak: KeycloakAdmin,
        press: PressClient,
        tenant_client: TenantClient,
        store: Store,
        max_attempts: int = 3,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        self._issuer = issuer
        self._realm = realm
        self._tenants = tuple(tenants)
        self._keycloak = keycloak
        self._press = press
        self._tenant_client = tenant_client
        self._store = store
        self._max_attempts = max_attempts
        self._sleep = sleep

    def handle(self, event: Event, *, dry_run: bool = False) -> EventResult:
        """Olayı işler. `dry_run` doğruysa yalnız okur ve önizleme döner."""
        if not is_handled(event) or event.realm != self._realm:
            return EventResult("ignored")
        if dry_run:
            try:
                return EventResult("preview", previews=tuple(a.preview() for a in self._plan(event)))
            except _Failed:
                return EventResult("failed")
        if self._store.is_processed(event.id):
            # Olay kuyrukta kalmışsa kalıntıdır. Kalıntı yeniden işlemeyi sonsuza dek başarısız gösterir.
            self._store.remove_dead_letter(event.id)
            return EventResult("duplicate")
        try:
            names = self._run(event)
        except _Failed as failure:
            self._store.add_dead_letter(event, str(failure))
            return EventResult("dead_lettered")
        self._store.mark_processed(event.id, "processed")
        return EventResult("processed", actions=tuple(names))

    def replay_dead_letters(self, *, dry_run: bool = False) -> list[tuple[str, EventResult]]:
        """Bekleme kuyruğundaki olayları bir kez yeniden işler. Bu iş elle başlatılır."""
        return [(letter.event.id, self.handle(letter.event, dry_run=dry_run)) for letter in self._store.dead_letters()]

    def _plan(self, event: Event) -> tuple[Action, ...]:
        subject = event.user_id or ""
        snapshot = self._retry("keycloak.read", lambda: self._keycloak.get_user_snapshot(subject))
        organization = None
        if event.type in MEMBERSHIP_TYPES and event.organization_id:
            org_id = event.organization_id
            organization = self._retry("keycloak.read", lambda: self._keycloak.get_organization(org_id))
        return plan_actions(
            event, snapshot, issuer=self._issuer, tenants=self._tenants, organization=organization
        )

    def _run(self, event: Event) -> list[str]:
        names: list[str] = []
        for _pass in range(_MAX_PASSES):
            actions = self._plan(event)
            failures: list[str] = []
            for action in actions:
                preview = action.preview()
                # Başarısız adım öteki adımları durdurmaz. Örneğin Press yanıt vermese de
                # kullanıcı bütün kiracılarda kapanır. Adımlar tekrar edilebilir.
                try:
                    self._retry(f"{preview.operation} {preview.target}", lambda action=action: self._execute(action))
                except _Failed as failure:
                    failures.append(str(failure))
                else:
                    names.append(preview.operation)
            if failures:
                raise _Failed("; ".join(failures))
            if not any(isinstance(action, EnsureOrganization) for action in actions):
                break
        return names

    def _execute(self, action: Action) -> None:
        if isinstance(action, EnsureOrganization):
            self._keycloak.ensure_organization_with_member(action.alias, action.name, action.subject)
        elif isinstance(action, PressEnsureTeam):
            self._press.ensure_team(action)
        elif isinstance(action, PressRemoveTeamMember):
            self._press.remove_team_member(action)
        elif isinstance(action, TenantProvision):
            self._tenant_client.provision(action)
        elif isinstance(action, TenantSetEnabled):
            self._tenant_client.set_enabled(action)
        elif isinstance(action, TenantChangeEmail):
            self._tenant_client.change_email(action)
        else:  # pragma: no cover - yeni eylem türü eklenirse burada görünür
            raise TypeError(f"unknown action: {type(action).__name__}")

    def _retry(self, label: str, call: Callable[[], T]) -> T:
        """Geçici hatada sınırlı sayıda yeniden dener. Kalıcı hatada hemen bırakır."""
        for attempt in range(1, self._max_attempts + 1):
            try:
                return call()
            except HttpError as error:
                reason, transient = str(error), error.transient
            except TransportError as error:
                # Bu metinler sabittir. Yanıt gövdesi taşımaz.
                reason, transient = str(error) or "network error", True
            if not transient or attempt == self._max_attempts:
                raise _Failed(f"{label}: {reason}")
            self._sleep(_BACKOFF_SECONDS * 2 ** (attempt - 1))
        raise _Failed(f"{label}: no attempt made")
