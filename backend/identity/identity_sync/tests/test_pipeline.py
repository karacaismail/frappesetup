"""Olayın uçtan uca işlenmesinin testleri. Ağ çağrıları sahte sunucuya gider.

Beklenen uç adları ve alanlar `docs/sozlesmeler.md` dosyasının 2., 5. ve 6. bölümünden gelir.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event

from . import fakes
from .fakes import ORG_ID, SUBJECT, Stack, keycloak_user


def event(type_: str = "VERIFY_EMAIL", kind: str = "user", id_: str = "e-1", org: str | None = None) -> Event:
    return Event(id=id_, kind=kind, type=type_, realm="platform", time=1, user_id=SUBJECT, organization_id=org)


class PipelineCase(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)
        self.org = {"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}

    def add_member(self, **overrides: object) -> None:
        self.stack.keycloak.add_user(keycloak_user(**overrides), [self.org])


class ProvisionTest(PipelineCase):
    def test_verified_member_is_sent_to_press_and_tenant(self) -> None:
        self.add_member()

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.actions, ("press.ensure_team", "tenant.change_email", "tenant.provision"))
        (team,) = self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM)
        self.assertEqual(
            team.json(),
            {
                "issuer": self.stack.issuer,
                "subject": SUBJECT,
                "email": "ayse@example.test",
                "email_verified": True,
                "organization_id": ORG_ID,
                "organization_name": "kiraci1",
            },
        )
        (provision,) = self.stack.tenant.calls("POST", fakes.TENANT_PROVISION)
        # Alanlar sözleşmenin 5. bölümündeki `provision` tablosundan gelir.
        self.assertEqual(
            provision.json(),
            {
                "issuer": self.stack.issuer,
                "subject": SUBJECT,
                "email": "ayse@example.test",
                "email_verified": True,
                "first_name": "Ayşe",
                "last_name": "Örnek",
                "enabled": True,
            },
        )

    def test_each_target_gets_a_token_with_only_its_own_audience(self) -> None:
        # Servis belirteci yalnız bir `aud` değeri taşır (sözleşme, 2. bölüm).
        self.add_member()

        self.stack.app.processor.handle(event())

        (team,) = self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM)
        (provision,) = self.stack.tenant.calls("POST", fakes.TENANT_PROVISION)
        self.assertEqual(team.headers["authorization"], "Bearer token-for:aud-press")
        self.assertEqual(provision.headers["authorization"], "Bearer token-for:aud-site-kiraci1")
        admin_reads = self.stack.keycloak.calls("GET", f"{self.stack.keycloak.admin}/users/{SUBJECT}")
        self.assertEqual(admin_reads[0].headers["authorization"], f"Bearer token-for:{fakes.ADMIN_SCOPE}")

    def test_token_request_uses_client_credentials(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event())

        token_calls = self.stack.keycloak.calls("POST", "/realms/platform/protocol/openid-connect/token")
        scopes = sorted(call.form()["scope"][0] for call in token_calls)
        self.assertEqual(scopes, [fakes.ADMIN_SCOPE, "aud-press", "aud-site-kiraci1"])
        form = token_calls[0].form()
        self.assertEqual(form["grant_type"], ["client_credentials"])
        self.assertEqual(form["client_id"], ["identity-sync"])
        self.assertEqual(form["client_secret"], ["test-client-secret"])

    def test_token_is_reused_until_it_expires(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event(id_="e-1"))
        self.stack.app.processor.handle(event(id_="e-2"))

        token_calls = self.stack.keycloak.calls("POST", "/realms/platform/protocol/openid-connect/token")
        self.assertEqual(len(token_calls), 3)

    def test_registration_creates_organization_then_team(self) -> None:
        keycloak = self.stack.keycloak
        keycloak.add_user(keycloak_user(), [])
        alias = f"t-{SUBJECT}"

        def create_org(req: fakes.Recorded) -> fakes.Reply:
            self.assertEqual(req.json(), {"name": alias, "alias": alias, "enabled": True})
            return 201, None, {"Location": f"{keycloak.url}{keycloak.admin}/organizations/{ORG_ID}"}

        def add_member(req: fakes.Recorded) -> fakes.Reply:
            self.assertEqual(req.json(), SUBJECT)
            keycloak.memberships[SUBJECT] = [{"id": ORG_ID, "name": alias, "alias": alias}]
            return 201, None

        keycloak.on("GET", f"{keycloak.admin}/organizations", (200, []))
        keycloak.on("POST", f"{keycloak.admin}/organizations", create_org)
        keycloak.on("POST", f"{keycloak.admin}/organizations/{ORG_ID}/members", add_member)

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "processed")
        self.assertEqual(result.actions, ("keycloak.ensure_organization", "press.ensure_team"))
        (team,) = self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM)
        self.assertEqual(team.json()["organization_id"], ORG_ID)

    def test_deleted_user_is_disabled_and_removed(self) -> None:
        self.stack.keycloak.remove_user(SUBJECT)

        result = self.stack.app.processor.handle(event("DELETE_ACCOUNT"))

        self.assertEqual(result.status, "processed")
        (removed,) = self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)
        # Source: docs/sozlesmeler.md, section 6. A deleted user's organizations can no longer be
        # read from Keycloak, so the request carries all_organizations instead of organization_id.
        # Press answers 400 to an empty organization_id, so the key must be absent, not null.
        self.assertEqual(
            removed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "all_organizations": True}
        )
        (disabled,) = self.stack.tenant.calls("POST", fakes.TENANT_SET_ENABLED)
        self.assertEqual(disabled.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "enabled": False})

    def test_email_change_renames_the_tenant_user_before_provision(self) -> None:
        # The tenant already knows the user under the old e-mail. Keycloak now has a new one.
        self.stack.tenant.seed_user(self.stack.issuer, SUBJECT, "eski@example.test")
        self.add_member(email="yeni@example.test")

        result = self.stack.app.processor.handle(event("UPDATE_EMAIL"))

        self.assertEqual(result.status, "processed")
        (changed,) = self.stack.tenant.calls("POST", fakes.TENANT_CHANGE_EMAIL)
        self.assertEqual(
            changed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "new_email": "yeni@example.test"}
        )
        # Rename first: the tenant rejects provision with 409 EmailMismatch while the old e-mail is linked.
        self.assertEqual([r.path for r in self.stack.tenant.writes()], [fakes.TENANT_CHANGE_EMAIL, fakes.TENANT_PROVISION])
        self.assertEqual(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["email"], "yeni@example.test")

    def test_new_user_without_link_is_provisioned(self) -> None:
        # No link yet: change_email answers 404 IdentityNotFound. That is not a failure. Provision creates the link.
        self.add_member()

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "processed")
        user = self.stack.tenant.user_of(self.stack.issuer, SUBJECT)
        self.assertEqual((user["email"], user["enabled"]), ("ayse@example.test", True))

    def test_404_without_identity_not_found_is_a_failure(self) -> None:
        # A wrong address also answers 404. Only the tenant's own IdentityNotFound means "no link".
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_CHANGE_EMAIL, (404, {"exc_type": "DoesNotExistError"}))

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "dead_lettered")
        self.assertIn("tenant.change_email kiraci1: HTTP 404", self.stack.app.store.dead_letters()[0].error)

    def test_membership_delete_resolves_organization(self) -> None:
        self.stack.keycloak.add_user(keycloak_user(), [])
        self.stack.keycloak.add_organization(ORG_ID, "kiraci1")

        result = self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        self.assertEqual(
            result.actions, ("press.remove_team_member", "tenant.set_enabled", "tenant.revoke_user_installations")
        )
        (removed,) = self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)
        self.assertEqual(removed.json()["organization_id"], ORG_ID)

    def test_disabled_member_is_removed_with_all_organizations(self) -> None:
        # Source: docs/sozlesmeler.md, section 6. Press disables the user and revokes the API keys
        # when it gets all_organizations. A disabled user gets one request, like a deleted user.
        self.add_member(enabled=False)

        self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        (removed,) = self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)
        self.assertEqual(
            removed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "all_organizations": True}
        )

    def test_removed_membership_names_one_organization(self) -> None:
        # The user is still enabled and only left one organization. This request never
        # carries all_organizations, so Press does not disable the user.
        self.stack.keycloak.add_user(keycloak_user(), [])
        self.stack.keycloak.add_organization(ORG_ID, "kiraci1")

        self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        (removed,) = self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)
        self.assertEqual(removed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "organization_id": ORG_ID})

    def test_empty_organization_id_is_never_sent(self) -> None:
        # Press answers 400 to an empty organization_id; it does not mean "all teams".
        from identity_sync.mapping import PressRemoveTeamMember

        action = PressRemoveTeamMember(issuer=self.stack.issuer, subject=SUBJECT, organization_id="")

        with self.assertRaises(ValueError):
            self.stack.app.press.remove_team_member(action)
        self.assertEqual(self.stack.press.requests, [])

    def test_team_reply_without_team_name_is_unknown(self) -> None:
        # `ensure_team` yanıtı `team` ve `created` alanlarını taşır (sözleşme, 6. bölüm).
        self.add_member()
        for reply in ((200, {"message": {"status": "done"}}), (200, {"message": {"team": "", "created": True}})):
            with self.subTest(reply=reply):
                self.stack.press.on("POST", fakes.PRESS_ENSURE_TEAM, reply)
                result = self.stack.app.processor.handle(event(id_=f"t-{reply[1]}"[:40].replace(" ", "")))
                self.assertEqual(result.status, "unknown")

    def test_other_realm_is_ignored(self) -> None:
        self.add_member()
        other = Event(id="e-9", kind="user", type="VERIFY_EMAIL", realm="baska", time=1, user_id=SUBJECT)

        result = self.stack.app.processor.handle(other)

        self.assertEqual(result.status, "ignored")
        self.assertEqual(self.stack.press.writes(), [])

    def test_unhandled_type_is_ignored_without_any_call(self) -> None:
        result = self.stack.app.processor.handle(event("LOGIN"))

        self.assertEqual(result.status, "ignored")
        self.assertEqual(self.stack.keycloak.requests, [])


class AmbiguousReadTest(PipelineCase):
    """Belirsiz Keycloak yanıtı kullanıcıyı kapatmamalıdır."""

    def assert_nothing_disabled(self, result) -> None:
        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(self.stack.press.writes() + self.stack.tenant.writes(), [])

    def test_404_from_wrong_realm_or_proxy_does_not_disable(self) -> None:
        # Kullanıcı ucu 404 döner. Realm'in kendisi de yanıt vermez. Bu silinme kanıtı değildir.
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users/{SUBJECT}", (404, None))
        kc.on("GET", f"{kc.admin}/users/count", (404, None))

        self.assert_nothing_disabled(self.stack.app.processor.handle(event()))

    def test_empty_200_does_not_disable(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users/{SUBJECT}", (200, None))

        self.assert_nothing_disabled(self.stack.app.processor.handle(event()))

    def test_user_without_enabled_field_does_not_disable(self) -> None:
        user = keycloak_user()
        del user["enabled"]
        self.stack.keycloak.add_user(user, [self.org])

        self.assert_nothing_disabled(self.stack.app.processor.handle(event()))

    def test_other_users_representation_does_not_disable(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users/{SUBJECT}", (200, {"id": "baska", "enabled": False}))

        self.assert_nothing_disabled(self.stack.app.processor.handle(event()))

    def test_failed_membership_read_does_not_deprovision(self) -> None:
        kc = self.stack.keycloak
        kc.add_user(keycloak_user(), [self.org])
        kc.add_organization(ORG_ID, "kiraci1")
        kc.on("GET", f"{kc.admin}/organizations/members/{SUBJECT}/organizations", (404, None))

        result = self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        self.assert_nothing_disabled(result)

    def test_confirmed_missing_user_is_deprovisioned(self) -> None:
        # Kullanıcı ucu 404 döner. Realm kullanıcı sayısını verir. Bu silinme kanıtıdır.
        # An administrator deleted the user. This event type reads the user's state.
        self.stack.keycloak.remove_user(SUBJECT)

        result = self.stack.app.processor.handle(event("USER_DELETE", "admin"))

        self.assertEqual(result.status, "processed")
        self.assertEqual(len(self.stack.keycloak.calls("GET", f"{self.stack.keycloak.admin}/users/count")), 1)


class FanOutTest(unittest.TestCase):
    def setUp(self) -> None:
        # A user that Keycloak disabled. Closing it on each target is independent work,
        # unlike the ordered deletion flow.
        self.stack = Stack(two_tenants=True)
        self.addCleanup(self.stack.close)
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [])

    def test_failing_press_does_not_stop_tenant_disable(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (503, None))

        result = self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_SET_ENABLED)), 1)
        self.assertEqual(len(self.stack.tenant2.calls("POST", fakes.TENANT_SET_ENABLED)), 1)

    def test_dead_letter_lists_every_failed_step(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (403, None))
        self.stack.tenant.on("POST", fakes.TENANT_SET_ENABLED, (404, None))

        self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        (letter,) = self.stack.app.store.dead_letters()
        self.assertIn("press.remove_team_member press: HTTP 403; tenant.set_enabled kiraci1: HTTP 404", letter.error)
        self.assertEqual(len(self.stack.tenant2.calls("POST", fakes.TENANT_SET_ENABLED)), 1)


class TargetContractTest(PipelineCase):
    """The fake targets follow the real contracts. These tests check the effect on the targets.

    Sources: contracts/press_tr.openapi.yaml, contracts/platform_core-kimlik.openapi.yaml and
    docs/sozlesmeler.md, section 6.
    """

    def seed_everywhere(self) -> None:
        self.stack.press.seed_member(self.stack.issuer, SUBJECT, "ayse@example.test", ORG_ID, api_keys=2)
        self.stack.press.seed_member(self.stack.issuer, SUBJECT, "ayse@example.test", "o-other")
        self.stack.press.users["ayse@example.test"]["api_keys"] = ["key-0", "key-1"]
        self.stack.tenant.seed_user(self.stack.issuer, SUBJECT, "ayse@example.test")

    def assert_closed_everywhere(self) -> None:
        press_user = self.stack.press.user_of(self.stack.issuer, SUBJECT)
        self.assertEqual(self.stack.press.teams_of(self.stack.issuer, SUBJECT), [])
        self.assertFalse(press_user["enabled"])
        self.assertEqual(press_user["api_keys"], [])
        self.assertFalse(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["enabled"])

    def test_disabled_user_is_closed_on_press_and_keys_are_revoked(self) -> None:
        self.seed_everywhere()
        self.add_member(enabled=False)

        result = self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        self.assertEqual(result.status, "processed")
        self.assert_closed_everywhere()

    def test_deleted_user_is_closed_on_press_and_keys_are_revoked(self) -> None:
        self.seed_everywhere()
        self.stack.keycloak.remove_user(SUBJECT)

        result = self.stack.app.processor.handle(event("DELETE_ACCOUNT"))

        self.assertEqual(result.status, "processed")
        self.assert_closed_everywhere()

    def test_disabled_user_loses_the_phone_installations(self) -> None:
        # Gap list, item 4: a closed user's phone installations are revoked too.
        self.seed_everywhere()
        self.stack.tenant.installations[(self.stack.issuer, SUBJECT)] = ["phone-1", "phone-2"]
        self.add_member(enabled=False)

        result = self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        self.assertEqual(result.status, "processed")
        self.assertNotIn((self.stack.issuer, SUBJECT), self.stack.tenant.installations)
        (revoked,) = self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)
        self.assertEqual(revoked.json(), {"issuer": self.stack.issuer, "subject": SUBJECT})

    def test_user_unknown_to_a_tenant_does_not_block_the_event(self) -> None:
        # The tenant answers 404 IdentityNotFound to set_enabled for a user it never had.
        self.stack.keycloak.remove_user(SUBJECT)

        result = self.stack.app.processor.handle(event("DELETE_ACCOUNT"))

        self.assertEqual(result.status, "processed")
        self.assertEqual(self.stack.app.store.dead_letters(), [])

    def test_leaving_one_organization_keeps_the_press_user_and_keys(self) -> None:
        self.seed_everywhere()
        self.stack.keycloak.add_user(keycloak_user(), [])
        self.stack.keycloak.add_organization(ORG_ID, "kiraci1")

        result = self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        self.assertEqual(result.status, "processed")
        press_user = self.stack.press.user_of(self.stack.issuer, SUBJECT)
        self.assertEqual(self.stack.press.teams_of(self.stack.issuer, SUBJECT), ["o-other"])
        self.assertTrue(press_user["enabled"])
        self.assertEqual(press_user["api_keys"], ["key-0", "key-1"])
        self.assertFalse(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["enabled"])

    def test_verified_member_ends_up_in_team_and_tenant(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event())

        self.assertEqual(self.stack.press.teams_of(self.stack.issuer, SUBJECT), [ORG_ID])
        self.assertTrue(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["enabled"])

    def test_same_event_content_twice_leaves_one_user_and_one_membership(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event(id_="e-1"))
        self.stack.app.processor.handle(event(id_="e-2"))

        self.assertEqual(len(self.stack.tenant.users), 1)
        self.assertEqual(len(self.stack.press.teams[ORG_ID]["members"]), 1)

    def test_success_body_of_another_shape_is_unknown(self) -> None:
        # Exact success bodies come from the target contracts. Anything else is not a success.
        self.add_member()
        wrong = {
            fakes.TENANT_PROVISION: {"message": {"user": "ayse@example.test", "enabled": False, "linked": True}},
            fakes.TENANT_CHANGE_EMAIL: {"message": {"user": "baska@example.test"}},
        }
        for index, (path, body) in enumerate(wrong.items()):
            with self.subTest(path=path):
                self.stack.tenant.on("POST", path, (200, body))
                result = self.stack.app.processor.handle(event(id_=f"w-{index}"))
                self.assertEqual(result.status, "unknown")
                self.stack.tenant.on("POST", path, fakes.DONE)

    def test_remove_reply_that_still_reports_membership_is_unknown(self) -> None:
        self.stack.keycloak.remove_user(SUBJECT)
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (200, {"message": {"team": None, "member": True}}))

        self.assertEqual(self.stack.app.processor.handle(event("DELETE_ACCOUNT")).status, "unknown")

    def test_disable_reply_that_reports_enabled_is_unknown(self) -> None:
        self.stack.keycloak.remove_user(SUBJECT)
        reply = (200, {"message": {"user": "ayse@example.test", "enabled": True}})
        self.stack.tenant.on("POST", fakes.TENANT_SET_ENABLED, reply)

        self.assertEqual(self.stack.app.processor.handle(event("DELETE_ACCOUNT")).status, "unknown")


class AccountDeletionTest(PipelineCase):
    """The deletion flow (docs/sozlesmeler.md, section 7; PROJE-KAYDI.md, O-27).

    The tenant and Press endpoints for installations and anonymizing are proposals.
    The fakes follow the Target schemas of this service's contract.
    """

    def setUp(self) -> None:
        super().setUp()
        issuer = self.stack.issuer
        self.add_member()
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID, api_keys=1)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        self.stack.tenant.users["ayse@example.test"].update(first_name="Ayşe", last_name="Örnek")
        self.stack.tenant.installations[(issuer, SUBJECT)] = ["phone-1"]

    def request(self, id_: str = "onay-s1") -> Event:
        return Event(id=id_, kind="request", type="ACCOUNT_DELETION", realm="platform", time=1, user_id=SUBJECT)

    def test_all_five_steps_run_in_order(self) -> None:
        result = self.stack.app.processor.handle(self.request())

        self.assertEqual(result.status, "processed")
        self.assertEqual(
            result.actions,
            (
                "keycloak.disable_user",
                "press.remove_team_member",
                "tenant.set_enabled",
                "tenant.revoke_user_installations",
                "press.anonymize_user",
                "tenant.anonymize_user",
                "keycloak.delete_user",
            ),
        )
        issuer, keycloak = self.stack.issuer, self.stack.keycloak
        self.assertNotIn(SUBJECT, keycloak.users)
        self.assertEqual(keycloak.logged_out, [SUBJECT])
        press_user = self.stack.press.user_of(issuer, SUBJECT)
        self.assertEqual((press_user["enabled"], press_user["api_keys"], press_user["anonymized"]), (False, [], True))
        tenant_user = self.stack.tenant.user_of(issuer, SUBJECT)
        self.assertEqual((tenant_user["enabled"], tenant_user["first_name"], tenant_user["anonymized"]), (False, "", True))
        self.assertNotIn((issuer, SUBJECT), self.stack.tenant.installations)

    def test_keycloak_user_is_disabled_before_it_is_deleted(self) -> None:
        keycloak = self.stack.keycloak

        self.stack.app.processor.handle(self.request())

        writes = [(r.method, r.path.rsplit("/", 2)[-2:]) for r in keycloak.requests if r.method != "GET" and "/admin/" in r.path]
        self.assertEqual(
            writes, [("PUT", ["users", SUBJECT]), ("POST", [SUBJECT, "logout"]), ("DELETE", ["users", SUBJECT])]
        )
        disable = keycloak.calls("PUT", f"{keycloak.admin}/users/{SUBJECT}")[0].json()
        self.assertIs(disable["enabled"], False)
        # The full representation is sent back, so no other field is wiped.
        self.assertEqual(disable["email"], "ayse@example.test")

    def test_record_keeps_no_personal_data_after_the_flow(self) -> None:
        import sqlite3

        self.stack.app.processor.handle(self.request())

        self.assertEqual(self.stack.app.store.dead_letters(), [])
        self.assertTrue(self.stack.app.store.is_processed("onay-s1"))
        dump = "\n".join(self.stack.app.store._db.iterdump())
        self.assertNotIn("example.test", dump)
        self.assertNotIn(SUBJECT, dump)
        self.assertIsInstance(self.stack.app.store._db, sqlite3.Connection)

    STEP_PATHS = (
        ("press", fakes.PRESS_REMOVE_MEMBER, []),
        ("tenant", fakes.TENANT_SET_ENABLED, ["keycloak.disable_user", "press.remove_team_member"]),
        (
            "tenant",
            fakes.TENANT_REVOKE_INSTALLATIONS,
            ["keycloak.disable_user", "press.remove_team_member", "tenant.set_enabled"],
        ),
        (
            "press",
            fakes.PRESS_ANONYMIZE,
            ["keycloak.disable_user", "press.remove_team_member", "tenant.set_enabled", "tenant.revoke_user_installations"],
        ),
    )

    def test_flow_stops_at_the_first_failed_step(self) -> None:
        # docs/sozlesmeler.md, section 7: the steps run in order. A later step never runs before
        # an earlier one is done. For example nothing is anonymized while installations remain.
        for index, (site, path, _done) in enumerate(self.STEP_PATHS):
            with self.subTest(path=path):
                stack = Stack()
                self.addCleanup(stack.close)
                stack.keycloak.add_user(keycloak_user(), [self.org])
                stack.press.seed_member(stack.issuer, SUBJECT, "ayse@example.test", ORG_ID)
                stack.tenant.seed_user(stack.issuer, SUBJECT, "ayse@example.test")
                getattr(stack, site).on("POST", path, (503, None))

                result = stack.app.processor.handle(self.request(f"onay-f{index}"))

                self.assertEqual(result.status, "dead_lettered")
                later = [later_path for _site, later_path, _d in self.STEP_PATHS[index + 1 :]]
                later += [fakes.TENANT_ANONYMIZE]
                called = [r.path for r in stack.press.writes() + stack.tenant.writes()]
                for later_path in later:
                    self.assertNotIn(later_path, called)
                self.assertIn(SUBJECT, stack.keycloak.users)
                self.assertEqual(stack.keycloak.calls("DELETE", f"{stack.keycloak.admin}/users/{SUBJECT}"), [])

    def test_unknown_outcome_stops_the_flow_too(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (202, {"message": {"status": "queued"}}))

        result = self.stack.app.processor.handle(self.request())

        self.assertEqual(result.status, "unknown")
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.stack.tenant.calls("POST", fakes.TENANT_ANONYMIZE), [])

    def test_retry_continues_from_the_step_that_failed(self) -> None:
        # The last step failed. A retry must not revoke installations or anonymize again.
        keycloak = self.stack.keycloak
        keycloak.on("DELETE", f"{keycloak.admin}/users/{SUBJECT}", (500, None))
        self.assertEqual(self.stack.app.processor.handle(self.request()).status, "dead_lettered")
        before = len(self.stack.press.writes() + self.stack.tenant.writes())
        keycloak.on("DELETE", f"{keycloak.admin}/users/{SUBJECT}", lambda _r: keycloak._delete_user(SUBJECT))

        results = self.stack.app.processor.replay_dead_letters()

        self.assertEqual([(r.status, r.actions) for _i, r in results], [("processed", ("keycloak.delete_user",))])
        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), before)
        self.assertNotIn(SUBJECT, keycloak.users)

    def test_retry_preview_shows_only_the_remaining_steps(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        self.stack.app.processor.handle(self.request())

        ((_id, preview),) = self.stack.app.processor.replay_dead_letters(dry_run=True)

        self.assertEqual([p.operation for p in preview.previews], ["tenant.anonymize_user", "keycloak.delete_user"])

    def test_same_request_sent_again_resumes_instead_of_starting_over(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        self.stack.app.processor.handle(self.request())
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, fakes.DONE)
        revokes = len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS))

        again = self.stack.app.processor.handle(self.request())

        self.assertEqual((again.status, again.actions), ("processed", ("tenant.anonymize_user", "keycloak.delete_user")))
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)), revokes)
        self.assertEqual(self.stack.app.processor.handle(self.request()).status, "duplicate")

    def test_lock_conflict_on_anonymize_is_retried(self) -> None:
        # docs/sozlesmeler.md, section 6: 409 means a lock conflict or timeout. The service retries.
        replies = iter([(409, None), (409, None)])

        def anonymize(_req: fakes.Recorded) -> fakes.Reply:
            return next(replies, fakes.DONE)

        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, anonymize)

        result = self.stack.app.processor.handle(self.request())

        self.assertEqual(result.status, "processed")
        self.assertEqual(len(self.stack.press.calls("POST", fakes.PRESS_ANONYMIZE)), 3)

    def test_anonymize_reply_must_follow_the_contract(self) -> None:
        # The old proposed body had no `found` field. It is no longer a success.
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (200, {"message": {"anonymized": True}}))

        self.assertEqual(self.stack.app.processor.handle(self.request()).status, "unknown")

    # --- one job per account (docs/sozlesmeler.md, section 7) ---

    def job(self) -> Event:
        return self.stack.app.processor.account_job(SUBJECT, time=1)

    def target_writes(self) -> int:
        return len(self.stack.press.writes() + self.stack.tenant.writes())

    def test_job_id_is_a_keyed_digest_of_the_account(self) -> None:
        job = self.job()

        self.assertRegex(job.id, r"^del-[0-9a-f]{40}$")
        self.assertNotIn(SUBJECT, job.id)
        self.assertEqual(job.id, self.stack.app.processor.account_job(SUBJECT, time=99).id)
        self.assertNotEqual(job.id, self.stack.app.processor.account_job("someone-else", time=1).id)

    def test_keycloak_delete_event_of_a_finished_job_starts_no_second_job(self) -> None:
        # Step 5 deletes the Keycloak user. The event listener reports that delete.
        self.assertEqual(self.stack.app.processor.handle(self.job()).status, "processed")
        before = self.target_writes()

        result = self.stack.app.processor.handle(event("USER_DELETE", "admin"))

        self.assertEqual(result.status, "duplicate")
        self.assertEqual(self.target_writes(), before)
        self.assertEqual(self.stack.app.store.dead_letters(), [])

    def test_delete_event_continues_the_job_press_started(self) -> None:
        # The Press request stopped at step 4. Then an administrator deleted the user in Keycloak.
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        self.assertEqual(self.stack.app.processor.handle(self.job()).status, "dead_lettered")
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, fakes.DONE)
        self.stack.keycloak.remove_user(SUBJECT)
        revokes = len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS))
        press_calls = len(self.stack.press.writes())

        result = self.stack.app.processor.handle(event("USER_DELETE", "admin"))

        # Only the step that was left runs. Finished steps are not called again.
        self.assertEqual((result.status, result.actions), ("processed", ("tenant.anonymize_user",)))
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)), revokes)
        self.assertEqual(len(self.stack.press.writes()), press_calls)
        self.assertEqual(self.stack.app.store.dead_letters(), [])
        self.assertEqual(self.stack.app.processor.handle(self.job()).status, "duplicate")

    def test_admin_delete_is_queued_as_the_account_job(self) -> None:
        self.stack.keycloak.remove_user(SUBJECT)
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (503, None))

        first = self.stack.app.processor.handle(event("USER_DELETE", "admin"))

        self.assertEqual(first.status, "dead_lettered")
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual((letter.event.id, letter.event.kind), (self.job().id, "request"))
        # The listener sends the event again with a new id. It is the same job.
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, fakes.DONE)
        revokes = len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS))
        again = Event(id="e-2", kind="admin", type="USER_DELETE", realm="platform", time=2, user_id=SUBJECT)

        second = self.stack.app.processor.handle(again)

        self.assertEqual((second.status, second.actions), ("processed", ("press.anonymize_user", "tenant.anonymize_user")))
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)), revokes)

    def test_delete_event_that_could_not_be_checked_becomes_the_job_on_replay(self) -> None:
        keycloak = self.stack.keycloak
        keycloak.remove_user(SUBJECT)
        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", (500, None))
        self.assertEqual(self.stack.app.processor.handle(event("USER_DELETE", "admin")).status, "dead_lettered")
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.event.id, "e-1")
        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", (404, {"error": "User not found"}))

        ((_id, result),) = self.stack.app.processor.replay_dead_letters()

        self.assertEqual(result.status, "processed")
        self.assertEqual(self.stack.app.store.dead_letters(), [])
        self.assertEqual(self.stack.app.processor.handle(self.job()).status, "duplicate")

    def test_retry_preview_names_the_job_not_the_account(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        self.stack.app.processor.handle(self.job())

        ((_id, preview),) = self.stack.app.processor.replay_dead_letters(dry_run=True)

        text = " ".join(f"{p.operation} {p.target} {p.summary}" for p in preview.previews)
        self.assertNotIn(SUBJECT, text)
        self.assertIn(self.job().id, text)
        (letter,) = self.stack.app.store.dead_letters()
        self.assertNotIn(SUBJECT, letter.error)

    def test_user_that_was_found_but_not_anonymized_is_not_done(self) -> None:
        reply = {"message": {"anonymized": False, "found": True}}
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (200, reply))

        self.assertEqual(self.stack.app.processor.handle(self.request()).status, "unknown")
        self.assertIn(SUBJECT, self.stack.keycloak.users)

    def test_flow_is_repeatable_when_everything_is_already_gone(self) -> None:
        self.stack.app.processor.handle(self.request("onay-s1"))

        again = self.stack.app.processor.handle(self.request("onay-s2"))

        self.assertEqual(again.status, "processed")

    def test_user_unknown_to_the_targets_is_not_an_error(self) -> None:
        # Press answers found false. The tenant answers 404 IdentityNotFound. Both mean nothing to do.
        stack = Stack()
        self.addCleanup(stack.close)
        stack.keycloak.add_user(keycloak_user(), [])

        result = stack.app.processor.handle(self.request())

        self.assertEqual(result.status, "processed")
        self.assertNotIn(SUBJECT, stack.keycloak.users)

    def test_admin_delete_event_runs_steps_two_to_four(self) -> None:
        # An administrator deleted the user in Keycloak. The event still closes and anonymizes
        # the user on Press and on the tenant. There is no Keycloak write.
        keycloak = self.stack.keycloak
        keycloak.remove_user(SUBJECT)

        result = self.stack.app.processor.handle(event("USER_DELETE", "admin"))

        self.assertEqual(result.status, "processed")
        self.assertEqual(
            result.actions,
            (
                "press.remove_team_member",
                "tenant.set_enabled",
                "tenant.revoke_user_installations",
                "press.anonymize_user",
                "tenant.anonymize_user",
            ),
        )
        self.assertTrue(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["anonymized"])
        self.assertFalse(self.stack.press.user_of(self.stack.issuer, SUBJECT)["enabled"])
        self.assertEqual([r for r in keycloak.requests if r.method != "GET" and "/admin/" in r.path], [])

    def test_delete_event_while_the_user_still_exists_anonymizes_nothing(self) -> None:
        result = self.stack.app.processor.handle(event("USER_DELETE", "admin"))

        self.assertEqual(result.status, "processed")
        self.assertNotIn("tenant.anonymize_user", result.actions)
        self.assertNotIn("anonymized", self.stack.tenant.user_of(self.stack.issuer, SUBJECT))

    def test_preview_writes_nothing(self) -> None:
        result = self.stack.app.processor.handle(self.request(), dry_run=True)

        self.assertEqual(result.status, "preview")
        self.assertEqual(len(result.previews), 7)
        self.assertEqual(self.stack.press.writes() + self.stack.tenant.writes(), [])
        self.assertIn(SUBJECT, self.stack.keycloak.users)
        self.assertEqual(self.stack.app.store.dead_letters(), [])


class IdempotencyTest(PipelineCase):
    def test_same_event_twice_changes_nothing(self) -> None:
        self.add_member()

        first = self.stack.app.processor.handle(event())
        writes_after_first = len(self.stack.press.writes()) + len(self.stack.tenant.writes())
        second = self.stack.app.processor.handle(event())

        self.assertEqual(first.status, "processed")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(self.stack.press.writes()) + len(self.stack.tenant.writes()), writes_after_first)

    def test_same_change_under_new_id_sends_the_same_requests(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event(id_="e-1"))
        self.stack.app.processor.handle(event(id_="e-2"))

        first, second = self.stack.tenant.calls("POST", fakes.TENANT_PROVISION)
        self.assertEqual(first.json(), second.json())

    def test_duplicate_clears_leftover_dead_letter(self) -> None:
        # Süreç iki kayıt arasında durduysa olay hem işlenmiş hem kuyrukta görünür.
        self.add_member()
        self.stack.app.processor.handle(event())
        self.stack.app.store.add_dead_letter(event(), "kalıntı")

        results = self.stack.app.processor.replay_dead_letters()

        self.assertEqual([r.status for _id, r in results], ["duplicate"])
        self.assertEqual(self.stack.app.store.dead_letters(), [])

    def test_expired_token_is_refreshed_once(self) -> None:
        self.add_member()
        seen: list[str] = []

        def provision(req: fakes.Recorded) -> fakes.Reply:
            seen.append(req.headers["authorization"])
            return (401, None) if len(seen) == 1 else fakes.DONE

        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, provision)

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "processed")
        token_calls = self.stack.keycloak.calls("POST", "/realms/platform/protocol/openid-connect/token")
        self.assertEqual(sorted(c.form()["scope"][0] for c in token_calls).count("aud-site-kiraci1"), 2)


class FailureTest(PipelineCase):
    def test_failing_tenant_sends_event_to_dead_letters_after_retries(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, {"exc": "down"}))

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_PROVISION)), 3)
        self.assertEqual(len(self.stack.sleeps), 2)
        # Başarısız adım öteki adımları durdurmaz.
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_CHANGE_EMAIL)), 1)
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.event, event())
        self.assertEqual(letter.error, "tenant.provision kiraci1: HTTP 503")
        self.assertEqual(letter.attempts, 1)

    def test_rejected_request_is_not_retried(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (403, {"exc": "no"}))

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_PROVISION)), 1)

    def test_dead_letter_does_not_store_personal_data(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (500, {"exc": "ayse@example.test bulunamadı"}))

        self.stack.app.processor.handle(event())

        (letter,) = self.stack.app.store.dead_letters()
        self.assertNotIn("example.test", repr(letter))

    def test_keycloak_failure_goes_to_dead_letters(self) -> None:
        self.stack.keycloak.on("GET", f"{self.stack.keycloak.admin}/users/{SUBJECT}", (500, None))

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "dead_lettered")
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.error, "keycloak.read: HTTP 500")

    def test_replay_processes_dead_letter_and_empties_queue(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.stack.app.processor.handle(event())
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)

        results = self.stack.app.processor.replay_dead_letters()

        self.assertEqual([(event_id, r.status) for event_id, r in results], [("e-1", "processed")])
        self.assertEqual(self.stack.app.store.dead_letters(), [])
        self.assertEqual(self.stack.app.processor.handle(event()).status, "duplicate")

    def test_replay_keeps_event_that_still_fails(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.stack.app.processor.handle(event())

        results = self.stack.app.processor.replay_dead_letters()

        self.assertEqual([r.status for _id, r in results], ["dead_lettered"])
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.attempts, 2)


class UnknownOutcomeTest(PipelineCase):
    """Hedefin kesin başarı yanıtı `{"message": {"status": "done"}}` olur. Gerisi belirsizdir."""

    UNCLEAR = (
        (202, {"message": {"status": "queued"}}),
        (200, None),
        (200, {"message": {"status": "queued"}}),
        (200, {"message": None}),
        (200, {"exc": "x"}),
        (204, None),
    )

    def test_unclear_reply_is_not_recorded_as_processed(self) -> None:
        for index, reply in enumerate(self.UNCLEAR):
            with self.subTest(reply=reply):
                stack = Stack()
                self.addCleanup(stack.close)
                stack.keycloak.add_user(keycloak_user(), [self.org])
                stack.tenant.on("POST", fakes.TENANT_PROVISION, reply)

                result = stack.app.processor.handle(event(id_=f"u-{index}"))

                self.assertEqual(result.status, "unknown")
                (letter,) = stack.app.store.dead_letters()
                self.assertEqual(letter.state, "unknown")
                self.assertEqual(letter.error, "tenant.provision kiraci1: unknown outcome")
                # Belirsiz sonuçta kör tekrar yapılmaz.
                self.assertEqual(len(stack.tenant.calls("POST", fakes.TENANT_PROVISION)), 1)

    def test_redelivery_of_unknown_event_does_not_repeat_the_write(self) -> None:
        # Sonucu bilinmeyen olay yeniden gelirse servis yazmayı tekrarlamaz. Karar insanındır.
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (202, {"message": {"status": "queued"}}))
        self.stack.app.processor.handle(event())
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)
        writes = len(self.stack.press.writes() + self.stack.tenant.writes())

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "unknown")
        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), writes)
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual((letter.state, letter.attempts), ("unknown", 1))

    def test_unclear_transport_results_of_a_write_are_unknown(self) -> None:
        # İstek gitti ama yanıt okunamadı. İşin bitip bitmediği bilinmez. Kör tekrar yapılmaz.
        cases = {
            "html": (200, "<html>vekil sunucu sayfası</html>"),
            "bad-gateway": (502, None),
            "gateway-timeout": (504, None),
        }
        for name, reply in cases.items():
            with self.subTest(case=name):
                stack = Stack()
                self.addCleanup(stack.close)
                stack.keycloak.add_user(keycloak_user(), [self.org])
                stack.tenant.on("POST", fakes.TENANT_PROVISION, reply)

                result = stack.app.processor.handle(event(id_=name))

                self.assertEqual(result.status, "unknown")
                self.assertEqual(len(stack.tenant.calls("POST", fakes.TENANT_PROVISION)), 1)

    def test_dropped_connection_after_send_is_unknown(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DROP)

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "unknown")
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_PROVISION)), 1)

    def test_unreachable_target_is_a_plain_failure(self) -> None:
        # Bağlantı hiç kurulmadı. İstek gitmedi. Bu durum belirsiz değildir.
        import dataclasses

        from identity_sync.app import build_app
        from identity_sync.mapping import Tenant

        closed = fakes.FakeTenant()
        url = closed.url
        closed.close()
        self.add_member()
        settings = dataclasses.replace(
            self.stack.settings, tenants=(Tenant(name="kiraci1", base_url=url, organization="kiraci1"),)
        )
        app = build_app(settings, sleep=lambda _s: None)
        self.addCleanup(app.close)

        result = app.processor.handle(event())

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(app.store.dead_letters()[0].state, "failed")

    def test_replay_skips_unknown_events_unless_asked(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (202, {"message": {"status": "queued"}}))
        self.stack.app.processor.handle(event())
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)
        calls = len(self.stack.tenant.writes())

        skipped = self.stack.app.processor.replay_dead_letters()

        self.assertEqual([(i, r.status) for i, r in skipped], [("e-1", "unknown")])
        self.assertEqual(len(self.stack.tenant.writes()), calls)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

        replayed = self.stack.app.processor.replay_dead_letters(include_unknown=True)

        self.assertEqual([r.status for _i, r in replayed], ["processed"])
        self.assertEqual(self.stack.app.store.dead_letters(), [])

    def test_failure_and_unknown_together_stay_unknown(self) -> None:
        self.add_member()
        self.stack.press.on("POST", fakes.PRESS_ENSURE_TEAM, (403, None))
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (202, None))

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "unknown")
        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.error, "press.ensure_team press: HTTP 403; tenant.provision kiraci1: unknown outcome")


class ApprovedPlanTest(PipelineCase):
    """Onay katmanı bir planı onaylar. Servis yalnız o planı yürütür."""

    def queue_failed(self, id_: str = "e-1") -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.stack.app.processor.handle(event(id_=id_))
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)

    def digest(self) -> str:
        from identity_sync.pipeline import replay_report

        return self.stack.app.digest(replay_report(self.stack.app.processor.replay_dead_letters(dry_run=True)))

    def test_plan_that_became_destructive_after_the_preview_is_refused(self) -> None:
        # The approval showed "prepare the user". The user was disabled before the execution.
        from identity_sync.pipeline import PreviewChanged

        self.add_member()
        self.queue_failed()
        digest = self.digest()
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [self.org])
        writes = len(self.stack.press.writes() + self.stack.tenant.writes())

        with self.assertRaises(PreviewChanged):
            self.stack.app.processor.replay_dead_letters(expected_digest=digest)

        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), writes)
        self.assertEqual(self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER), [])
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

    def test_execution_writes_the_plan_it_checked_without_reading_again(self) -> None:
        # Between the last check and the write there is no second read. So the written plan
        # is exactly the checked one, even if Keycloak changes in between.
        self.add_member()
        self.queue_failed()
        digest = self.digest()
        keycloak = self.stack.keycloak
        reads = {"count": 0}

        def user_route(_req: fakes.Recorded) -> fakes.Reply:
            reads["count"] += 1
            # Only the first read during the execution sees the approved state.
            return 200, keycloak_user(email="ayse@example.test" if reads["count"] == 1 else "yeni@example.test")

        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", user_route)

        results = self.stack.app.processor.replay_dead_letters(expected_digest=digest)

        self.assertEqual([r.status for _i, r in results], ["processed"])
        self.assertEqual(reads["count"], 1)
        self.assertEqual(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["email"], "ayse@example.test")

    def test_one_changed_event_refuses_the_whole_request(self) -> None:
        # Two events wait. The plan of the second one changed after the preview.
        # Nothing may be written, not even for the first event.
        from identity_sync.pipeline import PreviewChanged

        other = "99999999-9999-4999-8999-999999999999"
        keycloak = self.stack.keycloak
        self.add_member()
        keycloak.add_user(keycloak_user(subject=other, email="ikinci@example.test"), [self.org])
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.stack.app.processor.handle(event(id_="e-1"))
        second = Event(id="e-2", kind="user", type="VERIFY_EMAIL", realm="platform", time=2, user_id=other)
        self.stack.app.processor.handle(second)
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)
        digest = self.digest()
        keycloak.add_user(keycloak_user(subject=other, email="degisti@example.test"), [self.org])
        writes = len(self.stack.press.writes() + self.stack.tenant.writes())

        with self.assertRaises(PreviewChanged):
            self.stack.app.processor.replay_dead_letters(expected_digest=digest)

        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), writes)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 2)

    def test_organization_that_appeared_after_the_preview_is_refused(self) -> None:
        # The preview said "create a new organization". Someone created one with that name meanwhile.
        # The member must not be added to that other organization under the old approval.
        from identity_sync.pipeline import PreviewChanged

        keycloak = self.stack.keycloak
        keycloak.add_user(keycloak_user(), [])
        alias = f"t-{SUBJECT}"
        keycloak.on("GET", f"{keycloak.admin}/organizations", (503, None))
        self.stack.app.processor.handle(event())
        keycloak.on("GET", f"{keycloak.admin}/organizations", (200, []))
        digest = self.digest()
        keycloak.on("GET", f"{keycloak.admin}/organizations", (200, [{"id": "o-stranger", "name": alias, "alias": alias}]))

        with self.assertRaises(PreviewChanged):
            self.stack.app.processor.replay_dead_letters(expected_digest=digest)
        self.assertEqual([r for r in keycloak.requests if r.method != "GET" and "/admin/" in r.path], [])

    def test_existing_organization_is_named_by_its_id_in_the_plan(self) -> None:
        keycloak = self.stack.keycloak
        keycloak.add_user(keycloak_user(), [])
        alias = f"t-{SUBJECT}"
        keycloak.on("GET", f"{keycloak.admin}/organizations", (200, [{"id": ORG_ID, "name": alias, "alias": alias}]))

        result = self.stack.app.processor.handle(event(), dry_run=True)

        (preview,) = result.previews
        self.assertEqual(preview.operation, "keycloak.ensure_organization")
        self.assertIn(ORG_ID, preview.summary)

    def test_event_whose_preview_failed_is_not_executed(self) -> None:
        # Önizleme üretilemedi. İnsan bu olayın planını görmedi.
        # Keycloak yürütme anında yanıt verse de servis bu olayı yürütmez.
        self.add_member()
        self.queue_failed()
        keycloak = self.stack.keycloak
        reads = {"count": 0}

        def user_route(_req: fakes.Recorded) -> fakes.Reply:
            reads["count"] += 1
            # 1. okuma: insanın gördüğü önizleme. 2. okuma: özet denetimi. İkisi de başarısız.
            return (403, None) if reads["count"] <= 2 else (200, keycloak_user())

        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", user_route)
        digest = self.digest()
        writes = len(self.stack.press.writes() + self.stack.tenant.writes())

        results = self.stack.app.processor.replay_dead_letters(expected_digest=digest)

        self.assertEqual([r.status for _i, r in results], ["failed"])
        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), writes)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

    def test_follow_up_actions_after_organization_need_a_new_preview(self) -> None:
        # Önizleme yalnız "kuruluşu aç" işini gösterdi. Takım işi önizlemede yoktu.
        keycloak = self.stack.keycloak
        keycloak.add_user(keycloak_user(), [])
        alias = f"t-{SUBJECT}"
        keycloak.on("GET", f"{keycloak.admin}/organizations", (503, None))
        self.stack.app.processor.handle(event())
        keycloak.on("GET", f"{keycloak.admin}/organizations", (200, []))
        keycloak.on(
            "POST", f"{keycloak.admin}/organizations", (201, None, {"Location": f"{keycloak.url}{keycloak.admin}/organizations/{ORG_ID}"})
        )

        def add_member(_req: fakes.Recorded) -> fakes.Reply:
            keycloak.memberships[SUBJECT] = [{"id": ORG_ID, "name": alias, "alias": alias}]
            return 201, None

        keycloak.on("POST", f"{keycloak.admin}/organizations/{ORG_ID}/members", add_member)

        first = self.stack.app.processor.replay_dead_letters(expected_digest=self.digest())

        self.assertEqual([r.status for _i, r in first], ["dead_lettered"])
        self.assertEqual(self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM), [])
        # Yeni önizleme takım işini gösterir. Onaydan sonra iş biter.
        second = self.stack.app.processor.replay_dead_letters(expected_digest=self.digest())
        self.assertEqual([r.status for _i, r in second], ["processed"])
        self.assertEqual(len(self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM)), 1)

    def test_changed_field_values_invalidate_the_approval(self) -> None:
        # The preview text stays the same when only the e-mail or the name changes.
        # The digest must still change, because those values are what gets written.
        changes = {"email": "yeni@example.test", "firstName": "Zeynep", "lastName": "Yeni"}
        for index, (field, value) in enumerate(changes.items()):
            with self.subTest(field=field):
                stack = Stack()
                self.addCleanup(stack.close)
                stack.keycloak.add_user(keycloak_user(), [self.org])
                stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
                stack.app.processor.handle(event(id_=f"f-{index}"))
                stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)
                from identity_sync.pipeline import PreviewChanged, replay_report

                preview = replay_report(stack.app.processor.replay_dead_letters(dry_run=True))
                digest = stack.app.digest(preview)
                stack.keycloak.add_user({**keycloak_user(), field: value}, [self.org])
                writes = len(stack.press.writes() + stack.tenant.writes())

                with self.assertRaises(PreviewChanged):
                    stack.app.processor.replay_dead_letters(expected_digest=digest)
                self.assertEqual(len(stack.press.writes() + stack.tenant.writes()), writes)

    def test_preview_report_carries_no_personal_data(self) -> None:
        import json

        from identity_sync.pipeline import replay_report

        self.add_member()
        self.queue_failed()

        report = json.dumps(replay_report(self.stack.app.processor.replay_dead_letters(dry_run=True)), ensure_ascii=False)

        self.assertRegex(report, r'"plan_digest": "[0-9a-f]{64}"')
        for personal in ("example.test", "Ayşe", "Örnek"):
            self.assertNotIn(personal, report)

    def test_approved_replay_runs_the_previewed_plan(self) -> None:
        self.add_member()
        self.queue_failed()

        results = self.stack.app.processor.replay_dead_letters(expected_digest=self.digest())

        self.assertEqual([r.status for _i, r in results], ["processed"])


class DisableDoesNotNeedMembershipTest(PipelineCase):
    """Closing a disabled account must not depend on the membership or organization reads."""

    def test_disabled_user_is_closed_when_membership_read_fails(self) -> None:
        keycloak = self.stack.keycloak
        self.stack.tenant.seed_user(self.stack.issuer, SUBJECT, "ayse@example.test")
        keycloak.add_user(keycloak_user(enabled=False), [self.org])
        keycloak.on("GET", f"{keycloak.admin}/organizations/members/{SUBJECT}/organizations", (500, None))

        result = self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        self.assertEqual(result.status, "processed")
        self.assertFalse(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["enabled"])
        self.assertEqual(len(self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)), 1)

    def test_disabled_user_is_closed_when_organization_read_fails(self) -> None:
        keycloak = self.stack.keycloak
        self.stack.tenant.seed_user(self.stack.issuer, SUBJECT, "ayse@example.test")
        keycloak.add_user(keycloak_user(enabled=False), [self.org])
        keycloak.on("GET", f"{keycloak.admin}/organizations/{ORG_ID}", (500, None))

        result = self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        self.assertEqual(result.status, "processed")
        self.assertFalse(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["enabled"])

    def test_deleted_user_is_closed_when_organization_read_fails(self) -> None:
        keycloak = self.stack.keycloak
        keycloak.remove_user(SUBJECT)
        keycloak.on("GET", f"{keycloak.admin}/organizations/{ORG_ID}", (500, None))

        result = self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        self.assertEqual(result.status, "processed")
        self.assertEqual(len(self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)), 1)


class InterruptedWorkTest(PipelineCase):
    """The process can die at any point. The event record must not be lost or silently repeated."""

    def test_death_after_a_write_leaves_the_event_unknown(self) -> None:
        # A target finished the write. The process died before it recorded the outcome.
        self.add_member()
        processor = self.stack.app.processor
        original = processor._execute

        def execute_then_die(action) -> None:
            original(action)
            raise KeyboardInterrupt

        processor._execute = execute_then_die
        with self.assertRaises(KeyboardInterrupt):
            processor.handle(event())
        processor._execute = original
        writes = len(self.stack.press.writes() + self.stack.tenant.writes())
        self.assertGreater(writes, 0)

        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.state, "unknown")
        # The same event arrives again. The service does not repeat the write blindly.
        self.assertEqual(processor.handle(event()).status, "unknown")
        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), writes)
        # A human checks the target and replays it on purpose.
        replayed = processor.replay_dead_letters(include_unknown=True)
        self.assertEqual([r.status for _i, r in replayed], ["processed"])

    def test_death_before_any_write_keeps_the_event_for_replay(self) -> None:
        # The event was accepted. The process died while it read Keycloak. Nothing was written.
        self.add_member()
        keycloak = self.stack.app.keycloak
        original = keycloak.get_user_snapshot

        def die(_subject: str):
            raise KeyboardInterrupt

        keycloak.get_user_snapshot = die
        with self.assertRaises(KeyboardInterrupt):
            self.stack.app.processor.handle(event())
        keycloak.get_user_snapshot = original

        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual((letter.state, letter.attempts), ("failed", 0))
        self.assertEqual(self.stack.press.writes() + self.stack.tenant.writes(), [])
        replayed = self.stack.app.processor.replay_dead_letters()
        self.assertEqual([r.status for _i, r in replayed], ["processed"])

    def test_failed_event_counts_one_attempt(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))

        self.stack.app.processor.handle(event())

        self.assertEqual(self.stack.app.store.dead_letters()[0].attempts, 1)

    def test_ignored_and_previewed_events_leave_no_record(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event("LOGIN"))
        self.stack.app.processor.handle(event(), dry_run=True)

        self.assertEqual(self.stack.app.store.dead_letters(), [])


class OrganizationPassTest(PipelineCase):
    def test_event_is_not_processed_when_membership_never_appears(self) -> None:
        # Kuruluş açıldı ama üyelik okunamıyor. Takım işi çalışmadı. Olay işlenmiş sayılmaz.
        keycloak = self.stack.keycloak
        keycloak.add_user(keycloak_user(), [])
        keycloak.on("GET", f"{keycloak.admin}/organizations", (200, []))
        keycloak.on(
            "POST", f"{keycloak.admin}/organizations", (201, None, {"Location": f"{keycloak.url}{keycloak.admin}/organizations/{ORG_ID}"})
        )
        keycloak.on("POST", f"{keycloak.admin}/organizations/{ORG_ID}/members", (201, None))

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "dead_lettered")
        self.assertFalse(self.stack.app.store.is_processed("e-1"))
        # The second pass must not create the organization a second time.
        self.assertEqual(len(keycloak.calls("POST", f"{keycloak.admin}/organizations")), 1)


class CrossProcessTest(unittest.TestCase):
    """Sunucu ve `replay-dead-letters` komutu ayrı süreçlerdir. Aynı kayıt dosyasını açarlar."""

    def setUp(self) -> None:
        import os
        import tempfile

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.server_side = Stack(os.path.join(self.dir.name, "db.sqlite3"))
        self.addCleanup(self.server_side.close)
        self.server_side.keycloak.add_user(keycloak_user(), [{"id": ORG_ID, "name": "kiraci1", "alias": "kiraci1"}])
        # İkinci süreç: aynı ayar, ayrı bağlantı.
        from identity_sync.app import build_app

        self.command_side = build_app(self.server_side.settings, sleep=lambda _s: None)
        self.addCleanup(self.command_side.close)

    def test_server_and_replay_do_not_run_the_same_event_twice(self) -> None:
        import threading
        import time

        tenant = self.server_side.tenant
        tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.server_side.app.processor.handle(event())
        entered, release = threading.Event(), threading.Event()

        def slow_provision(_req: fakes.Recorded) -> fakes.Reply:
            entered.set()
            release.wait(5)
            return fakes.DONE

        tenant.on("POST", fakes.TENANT_PROVISION, slow_provision)
        before = len(tenant.calls("POST", fakes.TENANT_PROVISION))
        statuses: dict[str, list[str]] = {}

        def replay() -> None:
            statuses["replay"] = [r.status for _i, r in self.command_side.processor.replay_dead_letters()]

        def deliver() -> None:
            statuses["server"] = [self.server_side.app.processor.handle(event()).status]

        first = threading.Thread(target=replay)
        first.start()
        self.assertTrue(entered.wait(5))
        second = threading.Thread(target=deliver)
        second.start()
        time.sleep(0.3)  # ikinci süreç kilitte beklemelidir
        self.assertEqual(len(tenant.calls("POST", fakes.TENANT_PROVISION)) - before, 1)
        release.set()
        first.join(10)
        second.join(10)

        self.assertEqual(statuses, {"replay": ["processed"], "server": ["duplicate"]})
        self.assertEqual(len(tenant.calls("POST", fakes.TENANT_PROVISION)) - before, 1)

    def test_signature_claim_does_not_wait_for_a_running_event(self) -> None:
        import threading
        import time

        tenant = self.server_side.tenant
        entered, release = threading.Event(), threading.Event()

        def slow_provision(_req: fakes.Recorded) -> fakes.Reply:
            entered.set()
            release.wait(5)
            return fakes.DONE

        tenant.on("POST", fakes.TENANT_PROVISION, slow_provision)
        worker = threading.Thread(target=lambda: self.command_side.processor.handle(event()))
        worker.start()
        self.assertTrue(entered.wait(5))
        started = time.monotonic()

        claimed = self.server_side.app.store.claim_signature("abc", now=1.0, expires_at=301.0)

        self.assertTrue(claimed)
        self.assertLess(time.monotonic() - started, 1.0)
        release.set()
        worker.join(10)

    def test_busy_lock_is_reported_and_nothing_is_written(self) -> None:
        import dataclasses
        import threading

        from identity_sync.app import build_app
        from identity_sync.store import Busy

        impatient = build_app(dataclasses.replace(self.server_side.settings, lock_timeout=0.2), sleep=lambda _s: None)
        self.addCleanup(impatient.close)
        tenant = self.server_side.tenant
        entered, release = threading.Event(), threading.Event()

        def slow_provision(_req: fakes.Recorded) -> fakes.Reply:
            entered.set()
            release.wait(5)
            return fakes.DONE

        tenant.on("POST", fakes.TENANT_PROVISION, slow_provision)
        worker = threading.Thread(target=lambda: self.command_side.processor.handle(event(id_="uzun")))
        worker.start()
        self.assertTrue(entered.wait(5))

        with self.assertRaises(Busy):
            impatient.processor.handle(event(id_="bekleyen"))

        release.set()
        worker.join(10)
        self.assertFalse(impatient.store.is_processed("bekleyen"))

    def test_events_of_one_user_are_serialized_across_processes(self) -> None:
        # Eski "açık" durumla başlayan süreç, kapatma işleminden sonra kullanıcıyı yeniden açamaz.
        import threading
        import time

        keycloak, tenant = self.server_side.keycloak, self.server_side.tenant
        entered, release = threading.Event(), threading.Event()

        def slow_provision(_req: fakes.Recorded) -> fakes.Reply:
            entered.set()
            release.wait(5)
            return fakes.DONE

        tenant.on("POST", fakes.TENANT_PROVISION, slow_provision)
        enable = threading.Thread(target=lambda: self.server_side.app.processor.handle(event(id_="ac")))
        enable.start()
        self.assertTrue(entered.wait(5))
        keycloak.add_user(keycloak_user(enabled=False), [])
        disable = threading.Thread(target=lambda: self.command_side.processor.handle(event("USER_UPDATE", "admin", "kapat")))
        disable.start()
        time.sleep(0.3)
        self.assertEqual(tenant.calls("POST", fakes.TENANT_SET_ENABLED), [])  # kapatma sırasını bekler
        release.set()
        enable.join(10)
        disable.join(10)

        # The disable ran after the provision, so the user ends up closed.
        paths = [write.path for write in tenant.writes()]
        self.assertLess(paths.index(fakes.TENANT_PROVISION), paths.index(fakes.TENANT_SET_ENABLED))
        self.assertEqual(tenant.calls("POST", fakes.TENANT_SET_ENABLED)[-1].json()["enabled"], False)
        self.assertFalse(tenant.user_of(self.server_side.issuer, SUBJECT)["enabled"])


class PreviewTest(PipelineCase):
    def test_dry_run_writes_nothing_and_remembers_nothing(self) -> None:
        self.add_member(enabled=False)

        result = self.stack.app.processor.handle(event("USER_UPDATE", "admin"), dry_run=True)

        self.assertEqual(result.status, "preview")
        self.assertEqual(
            [p.operation for p in result.previews],
            ["press.remove_team_member", "tenant.set_enabled", "tenant.revoke_user_installations"],
        )
        self.assertTrue(all(p.destructive for p in result.previews))
        self.assertEqual(self.stack.press.writes() + self.stack.tenant.writes(), [])
        self.assertEqual(self.stack.app.processor.handle(event("USER_UPDATE", "admin")).status, "processed")

    def test_replay_dry_run_keeps_queue(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.stack.app.processor.handle(event())
        calls_before = len(self.stack.tenant.writes())

        results = self.stack.app.processor.replay_dead_letters(dry_run=True)

        self.assertEqual([r.status for _id, r in results], ["preview"])
        self.assertEqual(len(self.stack.tenant.writes()), calls_before)
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)


if __name__ == "__main__":
    unittest.main()
