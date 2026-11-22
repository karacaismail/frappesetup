"""Event-to-action mapping tests.

Expected results come from section 4 of the decision site page `rail-4-keycloak.md`.
Field names come from sections 5 and 6 of `docs/sozlesmeler.md`.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event
from identity_sync.mapping import (
    EnsureOrganization,
    KeycloakDeleteUser,
    OrderedPlan,
    KeycloakDisableUser,
    PressAnonymizeUser,
    TenantAnonymizeUser,
    TenantRevokeUserInstallations,
    Organization,
    PressEnsureTeam,
    PressRemoveTeamMember,
    Tenant,
    TenantChangeEmail,
    TenantProvision,
    TenantSetEnabled,
    UserSnapshot,
    plan_actions,
)

ISSUER = "http://identity.localhost:6110/realms/platform"
SUB = "11111111-1111-4111-8111-111111111111"
ORG = Organization(id="22222222-2222-4222-8222-222222222222", alias="tenant1", name="Kiracı 1")
OTHER_ORG = Organization(id="33333333-3333-4333-8333-333333333333", alias="baska")
TENANTS = (
    Tenant(name="tenant1", base_url="http://tenant1.localhost:6111", organization="tenant1"),
    Tenant(name="tenant2", base_url="http://tenant2.localhost:6111", organization="tenant2"),
)


def event(kind: str, type_: str, organization_id: str | None = None) -> Event:
    return Event(
        id="e-1",
        kind=kind,
        type=type_,
        realm="platform",
        time=1795000000000,
        user_id=SUB,
        organization_id=organization_id,
    )


def user(*, verified: bool = True, enabled: bool = True, orgs: tuple[Organization, ...] = (ORG,)) -> UserSnapshot:
    return UserSnapshot(
        subject=SUB,
        email="ayse@example.test",
        email_verified=verified,
        enabled=enabled,
        first_name="Ayşe",
        last_name="Örnek",
        organizations=orgs,
    )


def plan(ev: Event, snapshot: UserSnapshot | None, organization: Organization | None = None):
    return plan_actions(ev, snapshot, issuer=ISSUER, tenants=TENANTS, organization=organization)


# Fields come from the organization-to-team mapping section of `docs/sozlesmeler.md`.
# `email_verified` is required by contracts/press_tr.openapi.yaml (ensure_team request).
TEAM = PressEnsureTeam(
    issuer=ISSUER,
    subject=SUB,
    email="ayse@example.test",
    email_verified=True,
    organization_id=ORG.id,
    organization_name="Kiracı 1",
)
PROVISION = TenantProvision(
    tenant="tenant1",
    issuer=ISSUER,
    subject=SUB,
    email="ayse@example.test",
    email_verified=True,
    first_name="Ayşe",
    last_name="Örnek",
    enabled=True,
)
CHANGE_EMAIL = TenantChangeEmail(tenant="tenant1", issuer=ISSUER, subject=SUB, new_email="ayse@example.test")
# Source: docs/sozlesmeler.md, section 6. Press disables the user and revokes the API keys
# when it gets all_organizations. So a deleted user and a disabled user get the same single request.
def close_on(tenant: str) -> tuple:
    """Closing a user on a tenant also revokes the phone installations there (gap list, item 4)."""
    return (
        TenantSetEnabled(tenant=tenant, issuer=ISSUER, subject=SUB, enabled=False),
        TenantRevokeUserInstallations(tenant=tenant, issuer=ISSUER, subject=SUB),
    )


DEPROVISION_EVERYWHERE = (
    PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None),
    *close_on("tenant1"),
    *close_on("tenant2"),
)
# Source: docs/sozlesmeler.md, section 7, and PROJE-KAYDI.md, O-27. The order is fixed.
ACCOUNT_DELETION = (
    KeycloakDisableUser(subject=SUB),
    PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None),
    *close_on("tenant1"),
    *close_on("tenant2"),
    PressAnonymizeUser(issuer=ISSUER, subject=SUB),
    TenantAnonymizeUser(tenant="tenant1", issuer=ISSUER, subject=SUB),
    TenantAnonymizeUser(tenant="tenant2", issuer=ISSUER, subject=SUB),
    KeycloakDeleteUser(subject=SUB),
)


class RegistrationTest(unittest.TestCase):
    def test_register_with_unverified_email_does_nothing(self) -> None:
        # The initial link requires a verified email address (AU-4).
        self.assertEqual(plan(event("user", "REGISTER"), user(verified=False, orgs=())), ())

    def test_verified_user_without_organization_gets_an_organization(self) -> None:
        # Registration flow: the service creates an Organization and adds the user.
        self.assertEqual(
            plan(event("user", "VERIFY_EMAIL"), user(orgs=())),
            (EnsureOrganization(alias=f"t-{SUB}", name=f"t-{SUB}", subject=SUB, organization_id=None),),
        )

    def test_verified_member_gets_team_and_tenant_user(self) -> None:
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), user()), (TEAM, CHANGE_EMAIL, PROVISION))

    def test_member_of_unknown_organization_gets_only_a_team(self) -> None:
        team = PressEnsureTeam(
            issuer=ISSUER,
            subject=SUB,
            email="ayse@example.test",
            email_verified=True,
            organization_id=OTHER_ORG.id,
            organization_name="",
        )
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), user(orgs=(OTHER_ORG,))), (team,))

    def test_admin_created_user_without_organization_gets_no_organization(self) -> None:
        # An own Organization is created only for a user who self-registers.
        self.assertEqual(plan(event("admin", "USER_CREATE"), user(orgs=())), ())


class EmailChangeTest(unittest.TestCase):
    def test_update_email_renames_user_on_tenant(self) -> None:
        # An email change is applied on the tenant through `change_email` (G-57).
        self.assertEqual(plan(event("user", "UPDATE_EMAIL"), user()), (TEAM, CHANGE_EMAIL, PROVISION))

    def test_unverified_new_email_is_not_applied(self) -> None:
        self.assertEqual(plan(event("user", "UPDATE_EMAIL"), user(verified=False)), ())


class RemovalTest(unittest.TestCase):
    def test_account_deletion_request_runs_the_full_deletion_flow(self) -> None:
        self.assertEqual(plan(event("request", "ACCOUNT_DELETION"), None), ACCOUNT_DELETION)

    def test_account_deletion_plan_does_not_depend_on_the_keycloak_state(self) -> None:
        # The user may still be enabled, already disabled or already gone. The steps are the same.
        request = event("request", "ACCOUNT_DELETION")
        for snapshot in (user(), user(enabled=False), user(verified=False, orgs=()), None):
            with self.subTest(snapshot=snapshot):
                self.assertEqual(plan(request, snapshot), ACCOUNT_DELETION)

    def test_keycloak_user_is_disabled_first_and_deleted_last(self) -> None:
        # docs/sozlesmeler.md, section 7: step 1 only disables. Step 5 deletes.
        actions = plan(event("request", "ACCOUNT_DELETION"), None)
        self.assertIsInstance(actions[0], KeycloakDisableUser)
        self.assertIsInstance(actions[-1], KeycloakDeleteUser)
        self.assertEqual(sum(isinstance(a, KeycloakDeleteUser) for a in actions), 1)
        first_anonymize = min(i for i, a in enumerate(actions) if isinstance(a, (PressAnonymizeUser, TenantAnonymizeUser)))
        last_close = max(i for i, a in enumerate(actions) if isinstance(a, (TenantSetEnabled, TenantRevokeUserInstallations)))
        self.assertLess(last_close, first_anonymize)

    def test_deletion_plans_are_ordered(self) -> None:
        # An ordered plan stops at the first step that is not done.
        self.assertIsInstance(plan(event("request", "ACCOUNT_DELETION"), None), OrderedPlan)
        self.assertNotIsInstance(plan(event("admin", "USER_UPDATE"), user(enabled=False)), OrderedPlan)

    def test_every_deletion_step_is_destructive(self) -> None:
        for action in plan(event("request", "ACCOUNT_DELETION"), None):
            with self.subTest(action=type(action).__name__):
                self.assertTrue(action.preview().destructive)
                self.assertNotIn("@", action.preview().summary)

    def test_request_kind_with_another_type_is_not_handled(self) -> None:
        self.assertEqual(plan(event("request", "VERIFY_EMAIL"), user()), ())

    def test_removal_job_gets_steps_two_to_four(self) -> None:
        # An administrator deleted the user in Keycloak. There is nothing left to disable or delete
        # there, but steps 2, 3 and 4 still run (docs/sozlesmeler.md, section 7).
        self.assertEqual(plan(event("request", "ACCOUNT_REMOVAL"), None), ACCOUNT_DELETION[1:-1])
        self.assertIsInstance(plan(event("request", "ACCOUNT_REMOVAL"), None), OrderedPlan)

    def test_delete_event_itself_never_plans_an_anonymization(self) -> None:
        # Only the account job anonymizes. The pipeline turns a confirmed delete event into that
        # job. A delete event that reaches the plan as an event only closes the user.
        for kind, type_ in (("admin", "USER_DELETE"), ("user", "DELETE_ACCOUNT")):
            with self.subTest(type=type_):
                self.assertEqual(plan(event(kind, type_), None), DEPROVISION_EVERYWHERE)

    def test_delete_event_for_a_user_that_still_exists_does_not_anonymize(self) -> None:
        # The event says "deleted" but Keycloak still has the user. The current state decides.
        actions = plan(event("admin", "USER_DELETE"), user())
        self.assertFalse(any(isinstance(a, (PressAnonymizeUser, TenantAnonymizeUser)) for a in actions))
        self.assertEqual(plan(event("admin", "USER_DELETE"), user(enabled=False)), DEPROVISION_EVERYWHERE)

    def test_other_event_for_a_missing_user_only_closes(self) -> None:
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), None), DEPROVISION_EVERYWHERE)

    def test_disabled_user_is_disabled_everywhere(self) -> None:
        self.assertEqual(plan(event("admin", "USER_UPDATE"), user(enabled=False)), DEPROVISION_EVERYWHERE)

    def test_disabled_user_in_two_organizations_gets_one_request_for_all(self) -> None:
        # One all_organizations request, not one request per organization.
        actions = plan(event("admin", "USER_UPDATE"), user(enabled=False, orgs=(ORG, OTHER_ORG)))
        removals = [a for a in actions if isinstance(a, PressRemoveTeamMember)]
        self.assertEqual(removals, [PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None)])

    def test_disabled_user_without_organization_is_still_disabled_on_press(self) -> None:
        # Press must disable the user and revoke the API keys even if no membership is left.
        actions = plan(event("admin", "USER_UPDATE"), user(enabled=False, orgs=()))
        self.assertEqual(actions, DEPROVISION_EVERYWHERE)

    def test_disabled_state_wins_over_event_type(self) -> None:
        # The user's current state decides the action, not the event name.
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), user(enabled=False)), DEPROVISION_EVERYWHERE)

    def test_membership_event_of_disabled_user_sends_all_organizations(self) -> None:
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        self.assertEqual(plan(ev, user(enabled=False), ORG), DEPROVISION_EVERYWHERE)


class AdminUpdateTest(unittest.TestCase):
    def test_admin_update_resyncs_user(self) -> None:
        self.assertEqual(plan(event("admin", "USER_UPDATE"), user()), (TEAM, CHANGE_EMAIL, PROVISION))

    def test_admin_create_of_verified_member_provisions(self) -> None:
        self.assertEqual(plan(event("admin", "USER_CREATE"), user()), (TEAM, CHANGE_EMAIL, PROVISION))


class MembershipTest(unittest.TestCase):
    def test_new_membership_provisions_that_organization(self) -> None:
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_CREATE", ORG.id)
        self.assertEqual(plan(ev, user(), ORG), (TEAM, CHANGE_EMAIL, PROVISION))

    def test_removed_membership_deprovisions_only_that_organization(self) -> None:
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        self.assertEqual(
            plan(ev, user(orgs=(OTHER_ORG,)), ORG),
            (
                PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=ORG.id),
                *close_on("tenant1"),
            ),
        )

    def test_late_delete_event_does_not_remove_current_member(self) -> None:
        # The event arrived late. The user is a member again. The current state applies.
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        self.assertEqual(plan(ev, user(), ORG), (TEAM, CHANGE_EMAIL, PROVISION))

    def test_membership_of_deleted_organization_disables_non_member_tenants(self) -> None:
        # The Organization was deleted. Its alias is unknown. The user is disabled on every tenant without membership.
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        tenant2 = Organization(id="o-2", alias="tenant2")
        self.assertEqual(
            plan(ev, user(orgs=(tenant2,)), None),
            (
                PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=ORG.id),
                *close_on("tenant1"),
            ),
        )

    def test_rename_comes_before_provision(self) -> None:
        # The tenant answers 409 EmailMismatch to provision when the linked user has another
        # e-mail (contracts/platform_core-kimlik.openapi.yaml). So the rename must run first.
        actions = plan(event("user", "UPDATE_EMAIL"), user())
        self.assertLess(actions.index(CHANGE_EMAIL), actions.index(PROVISION))

    def test_verify_after_admin_email_change_still_renames(self) -> None:
        # An administrator changed the email address. The user verified it later. The tenant must still rename the user (G-57).
        self.assertIn(CHANGE_EMAIL, plan(event("user", "VERIFY_EMAIL"), user()))

    def test_membership_event_without_organization_plans_nothing(self) -> None:
        # Without an organization id there is no team to name. An empty id must never reach Press.
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", None)
        self.assertEqual(plan(ev, user(orgs=()), None), ())

    def test_membership_of_unverified_user_waits(self) -> None:
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_CREATE", ORG.id)
        self.assertEqual(plan(ev, user(verified=False), ORG), ())


class OtherEventsTest(unittest.TestCase):
    def test_unhandled_type_does_nothing(self) -> None:
        self.assertEqual(plan(event("user", "LOGIN"), user()), ())

    def test_plan_is_repeatable(self) -> None:
        ev = event("user", "UPDATE_EMAIL")
        self.assertEqual(plan(ev, user()), plan(ev, user()))


class PreviewTest(unittest.TestCase):
    def test_disable_is_marked_destructive(self) -> None:
        preview = TenantSetEnabled(tenant="tenant1", issuer=ISSUER, subject=SUB, enabled=False).preview()
        self.assertTrue(preview.destructive)
        self.assertEqual(preview.operation, "tenant.set_enabled")
        self.assertEqual(preview.target, "tenant1")

    def test_provision_is_not_destructive_and_hides_email(self) -> None:
        preview = PROVISION.preview()
        self.assertFalse(preview.destructive)
        self.assertNotIn("ayse@example.test", preview.summary)

    def test_organization_preview_says_whether_it_creates_or_joins(self) -> None:
        # The approver must see the real target: a new organization, or an existing one by its id.
        new = EnsureOrganization(alias="t-x", name="t-x", subject=SUB, organization_id=None).preview()
        existing = EnsureOrganization(alias="t-x", name="t-x", subject=SUB, organization_id="o-77").preview()

        self.assertIn("Create", new.summary)
        self.assertNotIn("Create", existing.summary)
        self.assertIn("o-77", existing.summary)

    def test_digest_needs_the_key(self) -> None:
        # An unkeyed SHA-256 would let a reader test an e-mail guess offline. The digest is an HMAC.
        import hashlib
        import json

        from identity_sync.mapping import digest_of

        value = {"email": "ayse@example.test"}
        plain = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        first, second = digest_of(value, b"key-one"), digest_of(value, b"key-two")
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, second)
        self.assertNotIn(plain, (first, second))
        self.assertEqual(first, digest_of(dict(value), b"key-one"))
        with self.assertRaises(ValueError):
            digest_of(value, b"")

    def test_preview_tells_the_human_that_press_disables_the_user(self) -> None:
        # The approver must see the full effect: Press disables the user and revokes the API keys.
        everywhere = PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None).preview()
        one_team = PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=ORG.id).preview()

        self.assertIn("disable the user", everywhere.summary)
        self.assertIn("revoke the API keys", everywhere.summary)
        self.assertNotIn("disable", one_team.summary)
        self.assertIn(ORG.id, one_team.summary)

    def test_remove_team_member_is_destructive(self) -> None:
        self.assertTrue(PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None).preview().destructive)


if __name__ == "__main__":
    unittest.main()
