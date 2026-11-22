"""Tests for the reconcile comparison and its repair plan. Both are pure functions.

Rule: Keycloak is the source of truth (decision site, rail-4-keycloak.md, section 5).
The comparison only reports. A repair runs later through the preview and approval flow.
All users are made up.
"""

from __future__ import annotations

import unittest

from identity_sync.mapping import (
    Organization,
    PressEnsureTeam,
    PressRemoveTeamMember,
    Tenant,
    TenantChangeEmail,
    TenantProvision,
    TenantRevokeUserInstallations,
    TenantSetEnabled,
    UserSnapshot,
)
from identity_sync.reconcile import Difference, Identity, deleted_subjects, find_differences, plan_repairs

ISSUER = "http://kimlik.localhost:6110/realms/platform"
ORG = Organization(id="o-1", alias="kiraci1", name="Kiracı 1")
OTHER = Organization(id="o-2", alias="baska", name="Başka")
TENANTS = (Tenant(name="kiraci1", base_url="http://kiraci1.localhost:6111", organization="kiraci1"),)


def user(subject: str, *, orgs=(ORG,), verified: bool = True, enabled: bool = True, email: str | None = None):
    return UserSnapshot(
        subject=subject,
        email=email or f"{subject}@example.test",
        email_verified=verified,
        enabled=enabled,
        first_name="Ad",
        last_name="Soyad",
        organizations=tuple(orgs),
    )


def identity(subject: str, *, email: str | None = None, enabled: bool = True, issuer: str = ISSUER, orgs=()):
    return Identity(
        issuer=issuer,
        subject=subject,
        email=email or f"{subject}@example.test",
        enabled=enabled,
        organization_ids=tuple(orgs),
    )


def differences(users, press=(), tenant=()):
    return find_differences(users, press, {"kiraci1": tenant}, issuer=ISSUER, tenants=TENANTS)


def in_sync(subject: str = "a"):
    return [user(subject)], [identity(subject, orgs=("o-1",))], [identity(subject)]


class TenantDifferenceTest(unittest.TestCase):
    def test_everything_in_sync(self) -> None:
        self.assertEqual(differences(*in_sync()), [])

    def test_missing_link(self) -> None:
        users, press, _tenant = in_sync()
        self.assertEqual(differences(users, press, []), [Difference("kiraci1", "a", "missing")])

    def test_disabled_in_keycloak_but_enabled_on_tenant(self) -> None:
        found = differences([user("a", enabled=False)], [], [identity("a")])
        self.assertEqual(found, [Difference("kiraci1", "a", "closed_in_keycloak")])

    def test_deleted_in_keycloak_is_its_own_kind_on_the_tenant(self) -> None:
        # The record still names a user Keycloak no longer has. Enabled or not, the deletion is unfinished.
        for record in (identity("a"), identity("a", enabled=False)):
            with self.subTest(enabled=record.enabled):
                self.assertEqual(differences([], [], [record]), [Difference("kiraci1", "a", "deleted_in_keycloak")])

    def test_closed_everywhere_is_not_a_difference(self) -> None:
        # A closed user stays on the target as a disabled record. That is the expected end state (X-11).
        self.assertEqual(differences([user("a", enabled=False)], [], [identity("a", enabled=False)]), [])

    def test_enabled_on_tenant_without_membership(self) -> None:
        found = differences([user("a", orgs=(OTHER,))], [identity("a", orgs=("o-2",))], [identity("a")])
        self.assertEqual(found, [Difference("kiraci1", "a", "unexpected")])

    def test_member_disabled_on_tenant(self) -> None:
        users, press, _tenant = in_sync()
        found = differences(users, press, [identity("a", enabled=False)])
        self.assertEqual(found, [Difference("kiraci1", "a", "disabled")])

    def test_email_mismatch_ignores_case(self) -> None:
        users, press, _tenant = in_sync()
        self.assertEqual(differences(users, press, [identity("a", email="A@Example.test")]), [])
        found = differences(users, press, [identity("a", email="eski@example.test")])
        self.assertEqual(found, [Difference("kiraci1", "a", "email_mismatch")])

    def test_unverified_member_is_reported_but_not_expected(self) -> None:
        # The first link needs a verified e-mail (AU-4). The comparison does not ask for it.
        self.assertEqual(differences([user("a", verified=False)], [], []), [])
        found = differences([user("a", verified=False)], [], [identity("a")])
        self.assertEqual(found, [Difference("kiraci1", "a", "unverified_in_keycloak")])

    def test_record_of_another_issuer_is_reported(self) -> None:
        foreign = identity("z", issuer="http://baska.example.test/realms/x")
        self.assertEqual(differences([], [], [foreign]), [Difference("kiraci1", "z", "foreign_issuer")])
        self.assertEqual(differences([], [foreign], []), [Difference("press", "z", "foreign_issuer")])


class PressDifferenceTest(unittest.TestCase):
    def test_missing_team_membership(self) -> None:
        users, _press, tenant = in_sync()
        found = differences(users, [], tenant)
        self.assertEqual(found, [Difference("press", "a", "missing_team_membership", "o-1")])

    def test_wrong_team_membership(self) -> None:
        # Member of o-2 on Press, member of o-1 in Keycloak.
        users, _press, tenant = in_sync()
        found = differences(users, [identity("a", orgs=("o-2",))], tenant)
        self.assertEqual(
            found,
            [
                Difference("press", "a", "missing_team_membership", "o-1"),
                Difference("press", "a", "unexpected_team_membership", "o-2"),
            ],
        )

    def test_closed_in_keycloak_but_enabled_on_press(self) -> None:
        found = differences([user("a", enabled=False)], [identity("a", orgs=("o-1",))], [])
        self.assertEqual(found, [Difference("press", "a", "closed_in_keycloak")])

    def test_deleted_in_keycloak_is_its_own_kind_on_press(self) -> None:
        for record in (identity("a", orgs=("o-1",)), identity("a", enabled=False)):
            with self.subTest(enabled=record.enabled):
                self.assertEqual(differences([], [record], []), [Difference("press", "a", "deleted_in_keycloak")])

    def test_deleted_subjects_are_listed_once(self) -> None:
        found = differences([], [identity("a"), identity("b")], [identity("a")])
        self.assertEqual(deleted_subjects(found), ("a", "b"))
        self.assertEqual(deleted_subjects(differences(*in_sync())), ())

    def test_deleted_accounts_get_no_single_repair_action(self) -> None:
        # They are finished by the ordered account job, not by loose actions.
        found = [Difference("press", "a", "deleted_in_keycloak"), Difference("kiraci1", "a", "deleted_in_keycloak")]
        self.assertEqual(plan_repairs(found, [], issuer=ISSUER, tenants=TENANTS), ())

    def test_member_disabled_on_press(self) -> None:
        users, _press, tenant = in_sync()
        found = differences(users, [identity("a", enabled=False, orgs=("o-1",))], tenant)
        self.assertEqual(found, [Difference("press", "a", "disabled")])

    def test_email_mismatch_on_press(self) -> None:
        users, _press, tenant = in_sync()
        found = differences(users, [identity("a", email="eski@example.test", orgs=("o-1",))], tenant)
        self.assertEqual(found, [Difference("press", "a", "email_mismatch")])

    def test_press_user_without_team_and_without_keycloak_membership_is_fine(self) -> None:
        self.assertEqual(differences([user("a", orgs=())], [identity("a")], []), [])


class ReportShapeTest(unittest.TestCase):
    def test_difference_carries_no_email(self) -> None:
        users, press, _tenant = in_sync()
        (found,) = differences(users, press, [identity("a", email="eski@example.test")])
        self.assertNotIn("example.test", repr(found))
        self.assertEqual(found.to_dict(), {"target": "kiraci1", "subject": "a", "kind": "email_mismatch"})

    def test_team_difference_names_the_organization(self) -> None:
        users, _press, tenant = in_sync()
        (found,) = differences(users, [], tenant)
        self.assertEqual(found.to_dict()["organization_id"], "o-1")

    def test_order_is_stable(self) -> None:
        users = [user("b"), user("a")]
        found = differences(users, [], [])
        self.assertEqual(
            [(d.target, d.subject) for d in found], [("press", "a"), ("press", "b"), ("kiraci1", "a"), ("kiraci1", "b")]
        )


class RepairPlanTest(unittest.TestCase):
    def repairs(self, found, users):
        return plan_repairs(found, users, issuer=ISSUER, tenants=TENANTS)

    def sync_actions(self, subject: str = "a"):
        email = f"{subject}@example.test"
        return (
            TenantChangeEmail(tenant="kiraci1", issuer=ISSUER, subject=subject, new_email=email),
            TenantProvision(
                tenant="kiraci1",
                issuer=ISSUER,
                subject=subject,
                email=email,
                email_verified=True,
                first_name="Ad",
                last_name="Soyad",
                enabled=True,
            ),
        )

    def test_missing_disabled_and_mismatched_tenant_users_are_synced(self) -> None:
        for kind in ("missing", "disabled", "email_mismatch"):
            with self.subTest(kind=kind):
                actions = self.repairs([Difference("kiraci1", "a", kind)], [user("a")])
                self.assertEqual(actions, self.sync_actions())

    def test_closed_or_unexpected_tenant_user_is_disabled(self) -> None:
        # Closing a user on a tenant also revokes the phone installations there.
        disable = (
            TenantSetEnabled(tenant="kiraci1", issuer=ISSUER, subject="a", enabled=False),
            TenantRevokeUserInstallations(tenant="kiraci1", issuer=ISSUER, subject="a"),
        )
        closed = [user("a", enabled=False)]
        self.assertEqual(self.repairs([Difference("kiraci1", "a", "closed_in_keycloak")], closed), disable)
        self.assertEqual(self.repairs([Difference("kiraci1", "a", "unexpected")], [user("a", orgs=(OTHER,))]), disable)

    def test_team_membership_repairs(self) -> None:
        found = [
            Difference("press", "a", "missing_team_membership", "o-1"),
            Difference("press", "a", "unexpected_team_membership", "o-2"),
        ]
        self.assertEqual(
            self.repairs(found, [user("a")]),
            (
                PressEnsureTeam(
                    issuer=ISSUER,
                    subject="a",
                    email="a@example.test",
                    email_verified=True,
                    organization_id="o-1",
                    organization_name="Kiracı 1",
                ),
                PressRemoveTeamMember(issuer=ISSUER, subject="a", organization_id="o-2"),
            ),
        )

    def test_closed_press_user_gets_all_organizations(self) -> None:
        actions = self.repairs([Difference("press", "a", "closed_in_keycloak")], [user("a", enabled=False)])
        self.assertEqual(actions, (PressRemoveTeamMember(issuer=ISSUER, subject="a", organization_id=None),))

    def test_differences_without_a_safe_repair_plan_nothing(self) -> None:
        # No target endpoint re-enables a Press user or changes a Press e-mail. A human decides.
        manual = [
            Difference("press", "a", "disabled"),
            Difference("press", "a", "email_mismatch"),
            Difference("kiraci1", "a", "unverified_in_keycloak"),
        ]
        self.assertEqual(self.repairs(manual, [user("a")]), ())

    def test_disable_is_skipped_when_the_user_is_an_open_member_now(self) -> None:
        # The difference says "closed", but Keycloak shows an open member now. The plan must not close the user.
        for kind in ("closed_in_keycloak", "unexpected"):
            with self.subTest(kind=kind):
                self.assertEqual(self.repairs([Difference("kiraci1", "a", kind)], [user("a")]), ())
        self.assertEqual(self.repairs([Difference("press", "a", "closed_in_keycloak")], [user("a")]), ())

    def test_repairs_are_not_duplicated(self) -> None:
        found = [Difference("kiraci1", "a", "disabled"), Difference("kiraci1", "a", "email_mismatch")]
        self.assertEqual(self.repairs(found, [user("a")]), self.sync_actions())

    def test_record_of_another_issuer_is_left_alone(self) -> None:
        # The targets reject another issuer. Such a record needs a human.
        self.assertEqual(self.repairs([Difference("kiraci1", "z", "foreign_issuer")], []), ())

    def test_repair_is_skipped_when_the_user_changed_meanwhile(self) -> None:
        # The difference says "sync", but the user is closed now. The plan must not re-open the user.
        actions = self.repairs([Difference("kiraci1", "a", "missing")], [user("a", enabled=False)])
        self.assertEqual(actions, ())


if __name__ == "__main__":
    unittest.main()
