"""Reconcile: compare Keycloak with Press and the tenant sites, and plan the repairs.

This module is pure. It touches neither the network nor the disk.
Keycloak is the source of truth (decision site, rail-4-keycloak.md, section 5).
A difference record carries no e-mail. It names the user by the Keycloak `sub`.

The comparison only reports. A repair plan is a list of the same actions the event
pipeline uses. It runs later, through the preview and approval flow.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass

from identity_sync.mapping import (
    Action,
    PressEnsureTeam,
    PressRemoveTeamMember,
    Tenant,
    TenantChangeEmail,
    TenantProvision,
    UserSnapshot,
    close_on_tenant,
)

PRESS = "press"
DELETED = "deleted_in_keycloak"

# Kinds a tenant user is brought back in sync for.
_SYNC_KINDS = frozenset({"missing", "disabled", "email_mismatch"})
# Kinds an enabled tenant user is disabled for.
_DISABLE_KINDS = frozenset({"closed_in_keycloak", "unexpected"})


@dataclass(frozen=True)
class Identity:
    """A user record on a target.

    `organization_ids` is filled by Press: one id per team membership. `None` means the target
    did not say, and then team memberships are not compared. An empty `email` means the same
    for the e-mail. The shared contract lets a list row carry only issuer, subject and state.
    """

    issuer: str
    subject: str
    email: str
    enabled: bool
    organization_ids: tuple[str, ...] | None = ()


@dataclass(frozen=True)
class Difference:
    """One difference between Keycloak and a target.

    `target` is `press` or a tenant name. `kind` is one of:

    - `missing`: the user should be on the tenant but has no link there.
    - `disabled`: the user should be enabled on the target but is disabled there.
    - `email_mismatch`: the target has another e-mail.
    - `closed_in_keycloak`: disabled in Keycloak, still enabled on the target.
    - `deleted_in_keycloak`: Keycloak no longer has the user, but the target still has the record,
      enabled or not. The account deletion is unfinished there.
    - `unexpected`: enabled on the tenant, but not a member of the tenant's organization.
    - `unverified_in_keycloak`: enabled on the tenant, member, but the Keycloak e-mail is not verified.
    - `missing_team_membership`: member in Keycloak, not in the Press team of `organization_id`.
    - `unexpected_team_membership`: in the Press team of `organization_id`, not a member in Keycloak.
    - `foreign_issuer`: the record belongs to another identity server.
    """

    target: str
    subject: str
    kind: str
    organization_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        return {name: value for name, value in asdict(self).items() if value is not None}


def _is_open(user: UserSnapshot | None) -> bool:
    return user is not None and user.enabled and user.email_verified


def _is_open_member(user: UserSnapshot | None, tenant_name: str, tenants: Sequence[Tenant]) -> bool:
    """Is the user enabled in Keycloak and a member of this tenant's organization?"""
    if user is None or not user.enabled:
        return False
    aliases = {org.alias for org in user.organizations}
    return any(tenant.name == tenant_name and tenant.organization in aliases for tenant in tenants)


def _tenant_differences(
    tenant: Tenant, users: Mapping[str, UserSnapshot], actual: Iterable[Identity], issuer: str
) -> list[Difference]:
    found: dict[str, Identity] = {}
    differences: list[Difference] = []
    for identity in actual:
        if identity.issuer != issuer:
            differences.append(Difference(tenant.name, identity.subject, "foreign_issuer"))
        else:
            found[identity.subject] = identity
    for subject in sorted(set(users) | set(found)):
        user, record = users.get(subject), found.get(subject)
        if user is None:
            differences.append(Difference(tenant.name, subject, DELETED))
            continue
        is_member = user is not None and any(org.alias == tenant.organization for org in user.organizations)
        if _is_open(user) and is_member:
            assert user is not None
            if record is None:
                kind = "missing"
            elif not record.enabled:
                kind = "disabled"
            elif record.email and record.email.lower() != user.email.lower():
                kind = "email_mismatch"
            else:
                continue
        elif record is not None and record.enabled:
            # A disabled leftover is the expected end state (X-11). An enabled record is a difference.
            if user is None or not user.enabled:
                kind = "closed_in_keycloak"
            elif is_member:
                kind = "unverified_in_keycloak"
            else:
                kind = "unexpected"
        else:
            continue
        differences.append(Difference(tenant.name, subject, kind))
    return differences


def _press_differences(users: Mapping[str, UserSnapshot], actual: Iterable[Identity], issuer: str) -> list[Difference]:
    found: dict[str, Identity] = {}
    differences: list[Difference] = []
    for identity in actual:
        if identity.issuer != issuer:
            differences.append(Difference(PRESS, identity.subject, "foreign_issuer"))
        else:
            found[identity.subject] = identity
    for subject in sorted(set(users) | set(found)):
        user, record = users.get(subject), found.get(subject)
        if user is None:
            differences.append(Difference(PRESS, subject, DELETED))
            continue
        if not user.enabled:
            if record is not None and record.enabled:
                differences.append(Difference(PRESS, subject, "closed_in_keycloak"))
            continue
        if not user.email_verified:
            continue  # no first link without a verified e-mail (AU-4); nothing is expected yet
        wanted = {org.id for org in user.organizations}
        if record is not None and wanted:
            if not record.enabled:
                differences.append(Difference(PRESS, subject, "disabled"))
            elif record.email and record.email.lower() != user.email.lower():
                differences.append(Difference(PRESS, subject, "email_mismatch"))
        if record is not None and record.organization_ids is None:
            continue  # the target did not list team memberships, so none can be compared
        present = set(record.organization_ids or ()) if record is not None else set()
        differences += [Difference(PRESS, subject, "missing_team_membership", org) for org in sorted(wanted - present)]
        differences += [
            Difference(PRESS, subject, "unexpected_team_membership", org) for org in sorted(present - wanted)
        ]
    return differences


def find_differences(
    users: Iterable[UserSnapshot],
    press: Iterable[Identity],
    tenant_records: Mapping[str, Iterable[Identity]],
    *,
    issuer: str,
    tenants: Sequence[Tenant],
) -> list[Difference]:
    """Compare every Keycloak user with Press and with each tenant.

    `users` holds every Keycloak user of the realm, with their organizations.
    A subject that is on a target but not in `users` was deleted in Keycloak.
    The result is ordered: Press first, then the tenants in configured order, each by `sub`.
    """
    by_subject = {user.subject: user for user in users}
    differences = _press_differences(by_subject, press, issuer)
    for tenant in tenants:
        differences += _tenant_differences(tenant, by_subject, tenant_records.get(tenant.name, ()), issuer)
    return differences


def deleted_subjects(differences: Iterable[Difference]) -> tuple[str, ...]:
    """Users that Keycloak no longer has but a target still does, each once, in order.

    Each one is finished by its ordered account job, not by loose repair actions
    (docs/sozlesmeler.md, section 7).
    """
    return tuple(sorted({difference.subject for difference in differences if difference.kind == DELETED}))


def plan_repairs(
    differences: Iterable[Difference],
    users: Iterable[UserSnapshot],
    *,
    issuer: str,
    tenants: Sequence[Tenant],
) -> tuple[Action, ...]:
    """Turn differences into the actions that remove them.

    Only differences with a safe, existing target operation get an action. The rest stay
    in the report for a human: a disabled Press user, a Press e-mail, an unverified e-mail,
    a record of another issuer.

    Each action is checked against the user's current Keycloak state, so a plan never
    re-opens a closed user or closes an open member.
    """
    by_subject = {user.subject: user for user in users}
    tenant_names = {tenant.name for tenant in tenants}
    actions: list[Action] = []

    def add(*new: Action) -> None:
        actions.extend(action for action in new if action not in actions)

    for difference in differences:
        user = by_subject.get(difference.subject)
        subject = difference.subject
        if difference.target == PRESS:
            if difference.kind == "closed_in_keycloak" and (user is None or not user.enabled):
                add(PressRemoveTeamMember(issuer=issuer, subject=subject, organization_id=None))
            elif difference.kind == "unexpected_team_membership" and difference.organization_id:
                if user is not None and user.enabled:
                    add(PressRemoveTeamMember(issuer=issuer, subject=subject, organization_id=difference.organization_id))
            elif difference.kind == "missing_team_membership" and _is_open(user):
                assert user is not None
                for org in user.organizations:
                    if org.id == difference.organization_id:
                        add(
                            PressEnsureTeam(
                                issuer=issuer,
                                subject=subject,
                                email=user.email,
                                email_verified=True,
                                organization_id=org.id,
                                organization_name=org.name,
                            )
                        )
        elif difference.target in tenant_names:
            if difference.kind in _SYNC_KINDS and _is_open(user):
                assert user is not None
                add(
                    TenantChangeEmail(tenant=difference.target, issuer=issuer, subject=subject, new_email=user.email),
                    TenantProvision(
                        tenant=difference.target,
                        issuer=issuer,
                        subject=subject,
                        email=user.email,
                        email_verified=True,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        enabled=True,
                    ),
                )
            elif difference.kind in _DISABLE_KINDS and not _is_open_member(user, difference.target, tenants):
                add(*close_on_tenant(difference.target, issuer, subject))
    return tuple(actions)
