"""Olay ile eylem eşlemesi.

Bu modül saftır. Ağa ve diske dokunmaz.

Eylemi olayın adı değil kullanıcının Keycloak'taki güncel durumu belirler.
Bu yüzden aynı olay iki kez gelirse ya da geç gelirse sonuç değişmez.
Kuralların kaynağı karar sitesinin `rail-4-keycloak.md` sayfasının 4. bölümüdür.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from identity_sync.events import (
    ACCOUNT_DELETION,
    ACCOUNT_REMOVAL,
    MEMBERSHIP_TYPES,
    USER_REMOVED_TYPES,
    Event,
    is_handled,
)

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


def digest_of(value: object, key: bytes) -> str:
    """Keyed digest of a preview. The approval is bound to it.

    The execute request must carry the same digest. It no longer matches when the plan
    changed after the preview. The digest is an HMAC-SHA256 under a key only the service
    knows: an unkeyed hash would let a reader check a guessed e-mail against it.
    """
    if not key:
        raise ValueError("digest key must not be empty")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


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
    """Make the user a member of an organization.

    `organization_id` is the real Keycloak id of the organization the member is added to.
    None means the organization does not exist yet and is created. The plan step resolves it
    before the preview, so the preview and the digest name the real target. Execution never
    looks the organization up again.
    """

    alias: str
    name: str
    subject: str
    organization_id: str | None = None

    def preview(self) -> Preview:
        if self.organization_id is None:
            summary = f"Create organization {self.alias} and add user {self.subject} as member."
        else:
            summary = f"Add user {self.subject} to existing organization {self.organization_id} ({self.alias})."
        return Preview(
            operation="keycloak.ensure_organization", target=self.alias, summary=summary, destructive=False
        )


@dataclass(frozen=True)
class PressEnsureTeam:
    """Fields come from the ensure_team request in contracts/press_tr.openapi.yaml.

    No team name is sent. Press generates it. `organization_name` is left out when empty.
    """

    issuer: str
    subject: str
    email: str
    email_verified: bool
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

    `organization_id` set: only that organization's team. The user stays enabled on Press.
    `organization_id` None: every team, sent as `all_organizations: true`. That form is for a
    deleted or disabled user. Press then also disables the user and revokes the API keys.
    """

    issuer: str
    subject: str
    organization_id: str | None

    def preview(self) -> Preview:
        if self.organization_id:
            summary = f"Remove user {self.subject} from organization {self.organization_id} on Press."
        else:
            summary = f"Remove user {self.subject} from every team on Press, disable the user and revoke the API keys."
        return Preview(
            operation="press.remove_team_member",
            target="press",
            summary=summary,
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


@dataclass(frozen=True)
class TenantRevokeUserInstallations:
    """Revoke every phone installation of the user on a tenant and delete the notification bindings (CK-7)."""

    tenant: str
    issuer: str
    subject: str

    def preview(self) -> Preview:
        return Preview(
            operation="tenant.revoke_user_installations",
            target=self.tenant,
            summary=f"Revoke every phone installation of user {self.subject} on tenant {self.tenant}.",
            destructive=True,
        )


@dataclass(frozen=True)
class TenantAnonymizeUser:
    """Anonymize the personal fields of the user on a tenant. Business records stay (O-27)."""

    tenant: str
    issuer: str
    subject: str

    def preview(self) -> Preview:
        return Preview(
            operation="tenant.anonymize_user",
            target=self.tenant,
            summary=f"Close user {self.subject} on tenant {self.tenant} and anonymize the personal fields.",
            destructive=True,
        )


@dataclass(frozen=True)
class PressAnonymizeUser:
    issuer: str
    subject: str

    def preview(self) -> Preview:
        return Preview(
            operation="press.anonymize_user",
            target="press",
            summary=f"Close user {self.subject} on Press, revoke the API keys and anonymize the personal fields.",
            destructive=True,
        )


@dataclass(frozen=True)
class KeycloakDisableUser:
    subject: str

    def preview(self) -> Preview:
        return Preview(
            operation="keycloak.disable_user",
            target="keycloak",
            summary=f"Disable Keycloak user {self.subject} and end the user's sessions.",
            destructive=True,
        )


@dataclass(frozen=True)
class KeycloakDeleteUser:
    """Delete the Keycloak user. This is the last step and cannot be undone."""

    subject: str

    def preview(self) -> Preview:
        return Preview(
            operation="keycloak.delete_user",
            target="keycloak",
            summary=f"Delete Keycloak user {self.subject}. This cannot be undone.",
            destructive=True,
        )


Action = (
    EnsureOrganization
    | PressEnsureTeam
    | PressRemoveTeamMember
    | TenantProvision
    | TenantSetEnabled
    | TenantChangeEmail
    | TenantRevokeUserInstallations
    | TenantAnonymizeUser
    | PressAnonymizeUser
    | KeycloakDisableUser
    | KeycloakDeleteUser
)


def close_on_tenant(tenant: str, issuer: str, subject: str) -> list[Action]:
    """Disable the user on a tenant and revoke the phone installations there."""
    return [
        TenantSetEnabled(tenant=tenant, issuer=issuer, subject=subject, enabled=False),
        TenantRevokeUserInstallations(tenant=tenant, issuer=issuer, subject=subject),
    ]


class OrderedPlan(tuple):
    """A plan whose steps depend on each other.

    The pipeline stops at the first step that is not done and later continues from that step.
    A plain tuple is a plan of independent steps: every step is attempted.
    """

    __slots__ = ()


def _removal_steps(subject: str, issuer: str, tenants: Sequence[Tenant]) -> list[Action]:
    """Steps 2, 3 and 4 of the deletion flow: close the user everywhere, then anonymize."""
    actions: list[Action] = [PressRemoveTeamMember(issuer=issuer, subject=subject, organization_id=None)]
    for tenant in tenants:
        actions += close_on_tenant(tenant.name, issuer, subject)
    actions.append(PressAnonymizeUser(issuer=issuer, subject=subject))
    actions += [TenantAnonymizeUser(tenant=tenant.name, issuer=issuer, subject=subject) for tenant in tenants]
    return actions


def plan_account_deletion(subject: str, *, issuer: str, tenants: Sequence[Tenant]) -> OrderedPlan:
    """The account deletion flow (docs/sozlesmeler.md, section 7; PROJE-KAYDI.md, O-27).

    The order is fixed and every step is repeatable:
    1. disable the Keycloak user, 2. close the Press user, 3. close the user on every tenant
    and revoke the phone installations, 4. anonymize the personal fields, 5. delete the Keycloak user.
    Step 1 only disables. The Keycloak user is deleted in step 5, after everything else is done.
    The plan does not depend on the user's current state.
    """
    return OrderedPlan(
        [KeycloakDisableUser(subject=subject), *_removal_steps(subject, issuer, tenants), KeycloakDeleteUser(subject=subject)]
    )


def plan_removed_user(subject: str, *, issuer: str, tenants: Sequence[Tenant]) -> OrderedPlan:
    """Steps 2, 3 and 4 for a user that Keycloak no longer has.

    An administrator deleted the user in Keycloak. There is nothing left to disable or delete
    there, but the user is still closed and anonymized on Press and on the tenants.
    """
    return OrderedPlan(_removal_steps(subject, issuer, tenants))


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

    if event.type == ACCOUNT_DELETION:
        return plan_account_deletion(subject, issuer=issuer, tenants=tenants)

    if event.type == ACCOUNT_REMOVAL:
        return plan_removed_user(subject, issuer=issuer, tenants=tenants)

    if snapshot is None and event.type in USER_REMOVED_TYPES:
        # The event says the user was deleted and Keycloak confirms it. If Keycloak still had
        # the user, the plan below would follow that state and anonymize nothing.
        return plan_removed_user(subject, issuer=issuer, tenants=tenants)

    if snapshot is None or not snapshot.enabled:
        # Deleted or disabled: the user is disabled on every tenant and leaves every Press team (X-11).
        # One all_organizations request covers both cases. Press also disables the user and revokes
        # the API keys when it gets that request (docs/sozlesmeler.md, section 6).
        closing: list[Action] = [PressRemoveTeamMember(issuer=issuer, subject=subject, organization_id=None)]
        for tenant in tenants:
            closing += close_on_tenant(tenant.name, issuer, subject)
        return tuple(closing)

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
        removal: list[Action] = [PressRemoveTeamMember(issuer=issuer, subject=snapshot.subject, organization_id=org_id)]
        for tenant in tenants:
            if tenant.organization not in aliases:
                removal += close_on_tenant(tenant.name, issuer, snapshot.subject)
        return tuple(removal)
    org_tenants = [t for t in tenants if t.organization == organization.alias]
    if any(org.id == organization.id for org in snapshot.organizations):
        if not snapshot.email_verified:
            return ()
        actions: list[Action] = [_team(snapshot, issuer, organization)]
        for tenant in org_tenants:
            actions += _sync_on_tenant(snapshot, issuer, tenant.name)
        return tuple(actions)
    leaving: list[Action] = [
        PressRemoveTeamMember(issuer=issuer, subject=snapshot.subject, organization_id=organization.id)
    ]
    for tenant in org_tenants:
        leaving += close_on_tenant(tenant.name, issuer, snapshot.subject)
    return tuple(leaving)


def _team(snapshot: UserSnapshot, issuer: str, organization: Organization) -> PressEnsureTeam:
    return PressEnsureTeam(
        issuer=issuer,
        subject=snapshot.subject,
        email=snapshot.email,
        email_verified=snapshot.email_verified,
        organization_id=organization.id,
        organization_name=organization.name,
    )


def _sync_on_tenant(snapshot: UserSnapshot, issuer: str, tenant: str) -> list[Action]:
    """Bring the tenant user's e-mail up to date, then create or update the user.

    The tenant changes an e-mail only through `change_email` (G-57). The event name does not
    say whether the e-mail changed, so the rename is planned on every sync. The tenant does
    nothing when the e-mail is the same and answers IdentityNotFound when there is no link yet.

    The rename comes first: the tenant rejects `provision` with EmailMismatch while the link
    still points to the old e-mail (contracts/platform_core-kimlik.openapi.yaml).
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
    return [rename, provision]
