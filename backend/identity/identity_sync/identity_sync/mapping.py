"""Olay ile eylem eşlemesi.

Bu modül saftır. Ağa ve diske dokunmaz.

Eylemi olayın adı değil kullanıcının Keycloak'taki güncel durumu belirler.
Bu yüzden aynı olay iki kez gelirse ya da geç gelirse sonuç değişmez.
Kuralların kaynağı karar sitesinin `rail-4-keycloak.md` sayfasının 4. bölümüdür.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from identity_sync.events import MEMBERSHIP_TYPES, Event, is_handled

# Kendi kaydolan kullanıcıya Organization açan olaylar.
_SELF_REGISTRATION_TYPES = frozenset({"REGISTER", "VERIFY_EMAIL"})


@dataclass(frozen=True)
class Preview:
    """Bir yazma işinin önizlemesi. İnsan onayı bu metne bakar.

    Önizleme e-posta ve sır taşımaz. Kullanıcıyı `sub` kimliğiyle anar.
    """

    operation: str
    target: str
    summary: str
    destructive: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def digest_of(value: object) -> str:
    """Önizlemenin özetini döner. Onay bu özete bağlanır.

    Yürütme isteği aynı özeti taşımalıdır. Plan önizlemeden sonra değiştiyse özet tutmaz.
    """
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Organization:
    id: str
    alias: str
    name: str = ""


@dataclass(frozen=True)
class Tenant:
    """Bir kiracı sitesi. `organization`, kiracının Keycloak Organization takma adıdır."""

    name: str
    base_url: str
    organization: str


@dataclass(frozen=True)
class UserSnapshot:
    """Kullanıcının Keycloak'taki güncel durumu."""

    subject: str
    email: str
    email_verified: bool
    enabled: bool
    first_name: str
    last_name: str
    organizations: tuple[Organization, ...] = ()


@dataclass(frozen=True)
class EnsureOrganization:
    """Organization'ı açar ve kullanıcıyı üye yapar."""

    alias: str
    name: str
    subject: str

    def preview(self) -> Preview:
        return Preview(
            operation="keycloak.ensure_organization",
            target=self.alias,
            summary=f"Create organization {self.alias} if missing and add user {self.subject} as member.",
            destructive=False,
        )


@dataclass(frozen=True)
class PressEnsureTeam:
    """Alanlar `docs/sozlesmeler.md` dosyasının "Kuruluş ile takım eşlemesi" bölümünden gelir.

    Takım adı gönderilmez. Takım adını Press üretir. `organization_name` boşsa gönderilmez.
    """

    issuer: str
    subject: str
    email: str
    organization_id: str
    organization_name: str = ""

    def preview(self) -> Preview:
        return Preview(
            operation="press.ensure_team",
            target="press",
            summary=f"Ensure Press team and membership for user {self.subject} in organization {self.organization_id}.",
            destructive=False,
        )


@dataclass(frozen=True)
class PressRemoveTeamMember:
    """Remove the user from a Press team.

    `organization_id` set: only that organization's team. `organization_id` None: every team,
    sent as `all_organizations: true`. That form is for a deleted user.
    """

    issuer: str
    subject: str
    organization_id: str | None

    def preview(self) -> Preview:
        scope = f"organization {self.organization_id}" if self.organization_id else "every team"
        return Preview(
            operation="press.remove_team_member",
            target="press",
            summary=f"Remove user {self.subject} from {scope} on Press.",
            destructive=True,
        )


@dataclass(frozen=True)
class TenantProvision:
    tenant: str
    issuer: str
    subject: str
    email: str
    email_verified: bool
    first_name: str
    last_name: str
    enabled: bool

    def preview(self) -> Preview:
        return Preview(
            operation="tenant.provision",
            target=self.tenant,
            summary=f"Create or update user {self.subject} on tenant {self.tenant}.",
            destructive=False,
        )


@dataclass(frozen=True)
class TenantSetEnabled:
    tenant: str
    issuer: str
    subject: str
    enabled: bool

    def preview(self) -> Preview:
        verb = "Enable" if self.enabled else "Disable"
        return Preview(
            operation="tenant.set_enabled",
            target=self.tenant,
            summary=f"{verb} user {self.subject} on tenant {self.tenant}.",
            destructive=not self.enabled,
        )


@dataclass(frozen=True)
class TenantChangeEmail:
    tenant: str
    issuer: str
    subject: str
    new_email: str

    def preview(self) -> Preview:
        return Preview(
            operation="tenant.change_email",
            target=self.tenant,
            summary=f"Rename user {self.subject} on tenant {self.tenant} to the current Keycloak email.",
            destructive=False,
        )


Action = (
    EnsureOrganization | PressEnsureTeam | PressRemoveTeamMember | TenantProvision | TenantSetEnabled | TenantChangeEmail
)


def plan_actions(
    event: Event,
    snapshot: UserSnapshot | None,
    *,
    issuer: str,
    tenants: Sequence[Tenant],
    organization: Organization | None = None,
) -> tuple[Action, ...]:
    """Olay için çalışacak eylemleri sırasıyla döner.

    `snapshot` kullanıcının güncel durumudur. Kullanıcı silindiyse `None` olur.
    `organization` üyelik olayındaki Organization'dır. Organization silindiyse `None` olur.
    """
    if not is_handled(event) or event.user_id is None:
        return ()
    subject = event.user_id

    if snapshot is None or not snapshot.enabled:
        # Silme ve kapatma: bütün sitelerde kullanıcı kapanır, Press üyeliği kalkar (X-11).
        if snapshot is None:
            # Silinen kullanıcının kuruluşları artık okunamaz. Üyelik kuruluş belirtilmeden kalkar.
            removals = [PressRemoveTeamMember(issuer=issuer, subject=subject, organization_id=None)]
        else:
            removals = [
                PressRemoveTeamMember(issuer=issuer, subject=subject, organization_id=org.id)
                for org in snapshot.organizations
            ]
        return (
            *removals,
            *(TenantSetEnabled(tenant=t.name, issuer=issuer, subject=subject, enabled=False) for t in tenants),
        )

    if event.type in MEMBERSHIP_TYPES:
        return _plan_membership(event, snapshot, issuer=issuer, tenants=tenants, organization=organization)

    if not snapshot.email_verified:
        # İlk bağ yalnız doğrulanmış e-postayla kurulur (AU-4).
        return ()

    if not snapshot.organizations:
        if event.type in _SELF_REGISTRATION_TYPES:
            alias = f"t-{subject}"
            return (EnsureOrganization(alias=alias, name=alias, subject=subject),)
        return ()

    aliases = {org.alias for org in snapshot.organizations}
    actions: list[Action] = [_team(snapshot, issuer, org) for org in snapshot.organizations]
    for tenant in tenants:
        if tenant.organization in aliases:
            actions += _sync_on_tenant(snapshot, issuer, tenant.name)
    return tuple(actions)


def _plan_membership(
    event: Event,
    snapshot: UserSnapshot,
    *,
    issuer: str,
    tenants: Sequence[Tenant],
    organization: Organization | None,
) -> tuple[Action, ...]:
    org_id = event.organization_id
    if not org_id:
        # No organization id, so there is no team to name. Press rejects an empty id.
        return ()
    if organization is None:
        # Organization silindi. Takma adı bilinmez. Kullanıcı üyesi olmadığı her kiracıda kapanır.
        aliases = {org.alias for org in snapshot.organizations}
        return (
            PressRemoveTeamMember(issuer=issuer, subject=snapshot.subject, organization_id=org_id),
            *(
                TenantSetEnabled(tenant=t.name, issuer=issuer, subject=snapshot.subject, enabled=False)
                for t in tenants
                if t.organization not in aliases
            ),
        )
    org_tenants = [t for t in tenants if t.organization == organization.alias]
    if any(org.id == organization.id for org in snapshot.organizations):
        if not snapshot.email_verified:
            return ()
        actions: list[Action] = [_team(snapshot, issuer, organization)]
        for tenant in org_tenants:
            actions += _sync_on_tenant(snapshot, issuer, tenant.name)
        return tuple(actions)
    return (
        PressRemoveTeamMember(issuer=issuer, subject=snapshot.subject, organization_id=organization.id),
        *(TenantSetEnabled(tenant=t.name, issuer=issuer, subject=snapshot.subject, enabled=False) for t in org_tenants),
    )


def _team(snapshot: UserSnapshot, issuer: str, organization: Organization) -> PressEnsureTeam:
    return PressEnsureTeam(
        issuer=issuer,
        subject=snapshot.subject,
        email=snapshot.email,
        organization_id=organization.id,
        organization_name=organization.name,
    )


def _sync_on_tenant(snapshot: UserSnapshot, issuer: str, tenant: str) -> list[Action]:
    """Kiracıda kaydı hazırlar, sonra e-postayı güncel değere getirir.

    Kiracı e-postayı yalnız `change_email` ile değiştirir (G-57). E-postanın değişip
    değişmediğini olayın adı söylemez. Bu yüzden `change_email` her eşitlemede çağrılır.
    E-posta aynıysa kiracı iş yapmaz.
    """
    provision = TenantProvision(
        tenant=tenant,
        issuer=issuer,
        subject=snapshot.subject,
        email=snapshot.email,
        email_verified=snapshot.email_verified,
        first_name=snapshot.first_name,
        last_name=snapshot.last_name,
        enabled=True,
    )
    rename = TenantChangeEmail(tenant=tenant, issuer=issuer, subject=snapshot.subject, new_email=snapshot.email)
    return [provision, rename]

