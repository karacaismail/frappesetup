"""Olayı işleyen akış.

Sıra şudur: kullanıcının güncel durumunu oku, eylemleri planla, eylemleri çalıştır.
Başarısız olay bekleme kuyruğuna girer. Kuyruk yalnız elle yeniden işlenir.
Bu modülde zamanlanmış iş ve yoklama döngüsü yoktur (Proje kaydı D-6).

Bir olayın işi iş kilidi altında yürür. Böylece sunucu ve `replay-dead-letters`
komutu aynı olayı birlikte çalıştıramaz. Aynı kullanıcının iki olayı da sıraya girer.
Geç kalan süreç kullanıcının durumunu yeniden okur. Kilit olay başına alınır.
Her kayıt hemen kalıcıdır. Yeniden işleme yarıda kesilirse biten olaylar kaybolmaz.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from identity_sync.events import MEMBERSHIP_TYPES, Event, is_handled
from identity_sync.httpjson import HttpError, TransportError, UnknownOutcome
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
    digest_of,
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
    """`status` değerleri sözleşmedeki `EventResult` şemasındadır."""

    status: str
    actions: tuple[str, ...] = ()
    previews: tuple[Preview, ...] = ()

    def to_dict(self) -> dict[str, object]:
        body: dict[str, object] = {"status": self.status, "actions": list(self.actions)}
        if self.status == "preview":
            body["previews"] = [preview.to_dict() for preview in self.previews]
        return body


ReplayResults = list[tuple[str, EventResult]]


def replay_report(results: ReplayResults) -> list[dict[str, object]]:
    return [{"event_id": event_id, **result.to_dict()} for event_id, result in results]


class PreviewChanged(Exception):
    """Plan önizlemeden sonra değişti. Onay eski plana aittir, yürütme yapılmaz."""


class _Failed(Exception):
    """Bir adım kalıcı olarak başarısız oldu. Metin kişisel veri taşımaz."""

    def __init__(self, message: str, *, unknown: bool = False) -> None:
        super().__init__(message)
        self.unknown = unknown


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

    def handle(
        self,
        event: Event,
        *,
        dry_run: bool = False,
        allow_unknown: bool = False,
        approved: tuple[Preview, ...] | None = None,
    ) -> EventResult:
        """Olayı işler.

        `dry_run` doğruysa yalnız okur ve önizleme döner.
        `allow_unknown`: sonucu bilinmeyen olayı yeniden çalıştırma izni. Bu, insanın açık kararıdır.
        `approved`: insanın onayladığı plan. Güncel plan bundan farklıysa servis hiçbir şey yazmaz.
        """
        if not is_handled(event) or event.realm != self._realm:
            return EventResult("ignored")
        if dry_run:
            try:
                return EventResult("preview", previews=tuple(a.preview() for a in self._plan(event)))
            except _Failed:
                return EventResult("failed")
        # Denetim, dış yazmalar ve kayıt tek iş kilidi altındadır.
        with self._store.work_lock():
            if self._store.is_processed(event.id):
                # Olay kuyrukta kalmışsa kalıntıdır. Kalıntı yeniden işlemeyi sonsuza dek başarısız gösterir.
                self._store.remove_dead_letter(event.id)
                return EventResult("duplicate")
            if not allow_unknown and self._store.dead_letter_state(event.id) == "unknown":
                # Olay yeniden geldi ama önceki sonucu bilinmiyor. Aynı hedefe kör tekrar yapılmaz.
                return EventResult("unknown")
            try:
                names = self._run(event, approved)
            except PreviewChanged:
                return EventResult("preview_changed")
            except _Failed as failure:
                # Sonucu bilinmeyen olay işlenmiş sayılmaz (`docs/sozlesmeler.md`, 10. bölüm).
                state = "unknown" if failure.unknown else "failed"
                self._store.add_dead_letter(event, str(failure), state=state)
                return EventResult("unknown" if failure.unknown else "dead_lettered")
            self._store.mark_processed(event.id, "processed")
            return EventResult("processed", actions=tuple(names))

    def replay_dead_letters(
        self, *, dry_run: bool = False, include_unknown: bool = False, expected_digest: str | None = None
    ) -> ReplayResults:
        """Bekleme kuyruğundaki olayları bir kez yeniden işler. Bu iş elle başlatılır.

        Sonucu bilinmeyen olaylar atlanır. Çünkü aynı hedefe kör tekrar yapılmaz.
        `include_unknown` doğruysa bu olaylar da işlenir. Bu, insanın açık kararıdır.

        `expected_digest` onaylanan önizlemenin özetidir. Özet tutmazsa `PreviewChanged`
        yükselir ve hiçbir olay işlenmez. Özet tutarsa her olay yalnız onaylanan planıyla
        yürür. Bir olayın planı arada değiştiyse o olay `preview_changed` sonucunu alır.
        Önizlemesi üretilemeyen olay yürütülmez.
        """
        letters = [
            letter for letter in self._store.dead_letters() if include_unknown or letter.state != "unknown"
        ]
        skipped: ReplayResults = [
            (letter.event.id, EventResult("unknown"))
            for letter in self._store.dead_letters()
            if letter.state == "unknown" and not include_unknown
        ]
        if dry_run or expected_digest is not None:
            previews: ReplayResults = [(letter.event.id, self.handle(letter.event, dry_run=True)) for letter in letters]
            ordered = self._ordered(previews + skipped)
            if dry_run:
                return ordered
            if digest_of(replay_report(ordered)) != expected_digest:
                raise PreviewChanged
            results: ReplayResults = []
            for letter, (_event_id, preview) in zip(letters, previews):
                if preview.status != "preview":
                    results.append((letter.event.id, preview))  # planı görülmeyen olay yürütülmez
                    continue
                result = self.handle(letter.event, allow_unknown=include_unknown, approved=preview.previews)
                results.append((letter.event.id, result))
            return self._ordered(results + skipped)
        results = [(letter.event.id, self.handle(letter.event, allow_unknown=include_unknown)) for letter in letters]
        return self._ordered(results + skipped)

    def _ordered(self, results: ReplayResults) -> ReplayResults:
        """Sonuçları kuyruk sırasına dizer. Özet bu sıraya bağlıdır."""
        order = {letter.event.id: index for index, letter in enumerate(self._store.dead_letters())}
        return sorted(results, key=lambda item: order.get(item[0], len(order)))

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

    def _run(self, event: Event, approved: tuple[Preview, ...] | None) -> list[str]:
        names: list[str] = []
        for pass_number in range(1, _MAX_PASSES + 1):
            actions = self._plan(event)
            if approved is not None:
                if pass_number > 1:
                    # Sonraki işler önizlemede yoktu. İnsan onları görmedi.
                    raise _Failed("follow-up actions need a new preview")
                if tuple(action.preview() for action in actions) != approved:
                    raise PreviewChanged
            failures: list[str] = []
            unknown = False
            for action in actions:
                preview = action.preview()
                label = f"{preview.operation} {preview.target}"
                # Başarısız adım öteki adımları durdurmaz. Örneğin Press yanıt vermese de
                # kullanıcı bütün kiracılarda kapanır. Adımlar tekrar edilebilir.
                try:
                    self._retry(label, lambda action=action: self._execute(action))
                except _Failed as failure:
                    failures.append(str(failure))
                except UnknownOutcome:
                    # Sonuç bilinmiyor. Kör tekrar yapılmaz.
                    failures.append(f"{label}: unknown outcome")
                    unknown = True
                else:
                    names.append(preview.operation)
            if failures:
                raise _Failed("; ".join(failures), unknown=unknown)
            if not any(isinstance(action, EnsureOrganization) for action in actions):
                return names
        # Organization açıldı ama üyelik hâlâ görünmüyor. Takım ve kiracı işleri çalışmadı.
        raise _Failed("keycloak.ensure_organization: membership not visible yet")

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
        """Geçici hatada sınırlı sayıda yeniden dener. Kalıcı hatada hemen bırakır.

        `UnknownOutcome` yeniden denenmez ve çağırana geçer.
        """
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
