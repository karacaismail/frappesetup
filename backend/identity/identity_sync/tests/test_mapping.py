"""Olay ile eylem eşlemesinin testleri.

Beklenen sonuçların kaynağı karar sitesinin `rail-4-keycloak.md` sayfasının 4. bölümüdür.
Alan adlarının kaynağı `docs/sozlesmeler.md` dosyasının 5. ve 6. bölümüdür.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event
from identity_sync.mapping import (
    EnsureOrganization,
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

ISSUER = "http://kimlik.localhost:6110/realms/platform"
SUB = "11111111-1111-4111-8111-111111111111"
ORG = Organization(id="22222222-2222-4222-8222-222222222222", alias="kiraci1", name="Kiracı 1")
OTHER_ORG = Organization(id="33333333-3333-4333-8333-333333333333", alias="baska")
TENANTS = (
    Tenant(name="kiraci1", base_url="http://kiraci1.localhost:6111", organization="kiraci1"),
    Tenant(name="kiraci2", base_url="http://kiraci2.localhost:6111", organization="kiraci2"),
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


# Alanlar `docs/sozlesmeler.md` dosyasının "Kuruluş ile takım eşlemesi" bölümünden gelir.
TEAM = PressEnsureTeam(
    issuer=ISSUER, subject=SUB, email="ayse@example.test", organization_id=ORG.id, organization_name="Kiracı 1"
)
PROVISION = TenantProvision(
    tenant="kiraci1",
    issuer=ISSUER,
    subject=SUB,
    email="ayse@example.test",
    email_verified=True,
    first_name="Ayşe",
    last_name="Örnek",
    enabled=True,
)
CHANGE_EMAIL = TenantChangeEmail(tenant="kiraci1", issuer=ISSUER, subject=SUB, new_email="ayse@example.test")
DISABLED_MEMBER = (
    PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=ORG.id),
    TenantSetEnabled(tenant="kiraci1", issuer=ISSUER, subject=SUB, enabled=False),
    TenantSetEnabled(tenant="kiraci2", issuer=ISSUER, subject=SUB, enabled=False),
)
# Silinen kullanıcının kuruluşları artık okunamaz. Üyelik kuruluş belirtilmeden kalkar.
DEPROVISION_EVERYWHERE = (
    PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None),
    TenantSetEnabled(tenant="kiraci1", issuer=ISSUER, subject=SUB, enabled=False),
    TenantSetEnabled(tenant="kiraci2", issuer=ISSUER, subject=SUB, enabled=False),
)


class RegistrationTest(unittest.TestCase):
    def test_register_with_unverified_email_does_nothing(self) -> None:
        # İlk bağ yalnız doğrulanmış e-postayla kurulur (AU-4).
        self.assertEqual(plan(event("user", "REGISTER"), user(verified=False, orgs=())), ())

    def test_verified_user_without_organization_gets_an_organization(self) -> None:
        # Kayıt akışı: servis Organization açar ve kullanıcıyı ekler.
        self.assertEqual(
            plan(event("user", "VERIFY_EMAIL"), user(orgs=())),
            (EnsureOrganization(alias=f"t-{SUB}", name=f"t-{SUB}", subject=SUB),),
        )

    def test_verified_member_gets_team_and_tenant_user(self) -> None:
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), user()), (TEAM, PROVISION, CHANGE_EMAIL))

    def test_member_of_unknown_organization_gets_only_a_team(self) -> None:
        team = PressEnsureTeam(
            issuer=ISSUER, subject=SUB, email="ayse@example.test", organization_id=OTHER_ORG.id, organization_name=""
        )
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), user(orgs=(OTHER_ORG,))), (team,))

    def test_admin_created_user_without_organization_gets_no_organization(self) -> None:
        # Kendi Organization'ı yalnız kendi kaydolan kullanıcıya açılır.
        self.assertEqual(plan(event("admin", "USER_CREATE"), user(orgs=())), ())


class EmailChangeTest(unittest.TestCase):
    def test_update_email_renames_user_on_tenant(self) -> None:
        # E-posta değişikliği kiracıda `change_email` ile uygulanır (G-57).
        self.assertEqual(plan(event("user", "UPDATE_EMAIL"), user()), (TEAM, PROVISION, CHANGE_EMAIL))

    def test_unverified_new_email_is_not_applied(self) -> None:
        self.assertEqual(plan(event("user", "UPDATE_EMAIL"), user(verified=False)), ())


class RemovalTest(unittest.TestCase):
    def test_deleted_account_is_disabled_everywhere(self) -> None:
        # Silme: bütün sitelerde kullanıcı kapanır ve Press üyeliği kalkar (X-11).
        self.assertEqual(plan(event("user", "DELETE_ACCOUNT"), None), DEPROVISION_EVERYWHERE)

    def test_admin_deleted_user_is_disabled_everywhere(self) -> None:
        self.assertEqual(plan(event("admin", "USER_DELETE"), None), DEPROVISION_EVERYWHERE)

    def test_disabled_user_is_disabled_everywhere(self) -> None:
        # Kapatılan kullanıcının kuruluşları bilinir. Üyelik her kuruluş için ayrı kalkar.
        self.assertEqual(plan(event("admin", "USER_UPDATE"), user(enabled=False)), DISABLED_MEMBER)

    def test_disabled_user_in_two_organizations_leaves_both_teams(self) -> None:
        actions = plan(event("admin", "USER_UPDATE"), user(enabled=False, orgs=(ORG, OTHER_ORG)))
        removed = [a.organization_id for a in actions if isinstance(a, PressRemoveTeamMember)]
        self.assertEqual(removed, [ORG.id, OTHER_ORG.id])

    def test_disabled_state_wins_over_event_type(self) -> None:
        # Eylemi olayın adı değil kullanıcının güncel durumu belirler.
        self.assertEqual(plan(event("user", "VERIFY_EMAIL"), user(enabled=False)), DISABLED_MEMBER)


class AdminUpdateTest(unittest.TestCase):
    def test_admin_update_resyncs_user(self) -> None:
        self.assertEqual(plan(event("admin", "USER_UPDATE"), user()), (TEAM, PROVISION, CHANGE_EMAIL))

    def test_admin_create_of_verified_member_provisions(self) -> None:
        self.assertEqual(plan(event("admin", "USER_CREATE"), user()), (TEAM, PROVISION, CHANGE_EMAIL))


class MembershipTest(unittest.TestCase):
    def test_new_membership_provisions_that_organization(self) -> None:
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_CREATE", ORG.id)
        self.assertEqual(plan(ev, user(), ORG), (TEAM, PROVISION, CHANGE_EMAIL))

    def test_removed_membership_deprovisions_only_that_organization(self) -> None:
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        self.assertEqual(
            plan(ev, user(orgs=(OTHER_ORG,)), ORG),
            (
                PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=ORG.id),
                TenantSetEnabled(tenant="kiraci1", issuer=ISSUER, subject=SUB, enabled=False),
            ),
        )

    def test_late_delete_event_does_not_remove_current_member(self) -> None:
        # Olay geç geldi. Kullanıcı yeniden üye. Güncel durum geçerlidir.
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        self.assertEqual(plan(ev, user(), ORG), (TEAM, PROVISION, CHANGE_EMAIL))

    def test_membership_of_deleted_organization_disables_non_member_tenants(self) -> None:
        # Organization silindi. Takma adı bilinmez. Kullanıcı üyesi olmadığı her kiracıda kapanır.
        ev = event("admin", "ORGANIZATION_MEMBERSHIP_DELETE", ORG.id)
        kiraci2 = Organization(id="o-2", alias="kiraci2")
        self.assertEqual(
            plan(ev, user(orgs=(kiraci2,)), None),
            (
                PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=ORG.id),
                TenantSetEnabled(tenant="kiraci1", issuer=ISSUER, subject=SUB, enabled=False),
            ),
        )

    def test_verify_after_admin_email_change_still_renames(self) -> None:
        # Yönetici e-postayı değiştirdi. Kullanıcı sonra doğruladı. Kiracıda ad yine değişmelidir (G-57).
        self.assertIn(CHANGE_EMAIL, plan(event("user", "VERIFY_EMAIL"), user()))

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
        preview = TenantSetEnabled(tenant="kiraci1", issuer=ISSUER, subject=SUB, enabled=False).preview()
        self.assertTrue(preview.destructive)
        self.assertEqual(preview.operation, "tenant.set_enabled")
        self.assertEqual(preview.target, "kiraci1")

    def test_provision_is_not_destructive_and_hides_email(self) -> None:
        preview = PROVISION.preview()
        self.assertFalse(preview.destructive)
        self.assertNotIn("ayse@example.test", preview.summary)

    def test_remove_team_member_is_destructive(self) -> None:
        self.assertTrue(PressRemoveTeamMember(issuer=ISSUER, subject=SUB, organization_id=None).preview().destructive)


if __name__ == "__main__":
    unittest.main()
