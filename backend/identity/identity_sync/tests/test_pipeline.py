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
        self.assertEqual(result.actions, ("press.ensure_team", "tenant.provision", "tenant.change_email"))
        (team,) = self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM)
        self.assertEqual(
            team.json(),
            {
                "issuer": self.stack.issuer,
                "subject": SUBJECT,
                "email": "ayse@example.test",
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
        self.assertEqual(admin_reads[0].headers["authorization"], "Bearer token-for:admin-api")

    def test_token_request_uses_client_credentials(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event())

        token_calls = self.stack.keycloak.calls("POST", "/realms/platform/protocol/openid-connect/token")
        scopes = sorted(call.form()["scope"][0] for call in token_calls)
        self.assertEqual(scopes, ["admin-api", "aud-press", "aud-site-kiraci1"])
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
        self.assertEqual(removed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "organization_id": None})
        (disabled,) = self.stack.tenant.calls("POST", fakes.TENANT_SET_ENABLED)
        self.assertEqual(disabled.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "enabled": False})

    def test_email_change_calls_change_email(self) -> None:
        self.add_member(email="yeni@example.test")

        self.stack.app.processor.handle(event("UPDATE_EMAIL"))

        (changed,) = self.stack.tenant.calls("POST", fakes.TENANT_CHANGE_EMAIL)
        self.assertEqual(
            changed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "new_email": "yeni@example.test"}
        )
        # Önce kayıt hazırlanır, sonra ad değişir. Yeni kullanıcıda `change_email` iş yapmaz.
        order = [r.path for r in self.stack.tenant.writes()]
        self.assertEqual(order, [fakes.TENANT_PROVISION, fakes.TENANT_CHANGE_EMAIL])

    def test_membership_delete_resolves_organization(self) -> None:
        self.stack.keycloak.add_user(keycloak_user(), [])
        self.stack.keycloak.add_organization(ORG_ID, "kiraci1")

        result = self.stack.app.processor.handle(event("ORGANIZATION_MEMBERSHIP_DELETE", "admin", org=ORG_ID))

        self.assertEqual(result.actions, ("press.remove_team_member", "tenant.set_enabled"))
        (removed,) = self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)
        self.assertEqual(removed.json()["organization_id"], ORG_ID)

    def test_disabled_member_leaves_team_by_organization_id(self) -> None:
        self.add_member(enabled=False)

        self.stack.app.processor.handle(event("USER_UPDATE", "admin"))

        (removed,) = self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER)
        self.assertEqual(removed.json(), {"issuer": self.stack.issuer, "subject": SUBJECT, "organization_id": ORG_ID})

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
        self.stack.keycloak.remove_user(SUBJECT)

        result = self.stack.app.processor.handle(event("DELETE_ACCOUNT"))

        self.assertEqual(result.status, "processed")
        self.assertEqual(len(self.stack.keycloak.calls("GET", f"{self.stack.keycloak.admin}/users/count")), 1)


class FanOutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = Stack(two_tenants=True)
        self.addCleanup(self.stack.close)
        self.stack.keycloak.remove_user(SUBJECT)

    def test_failing_press_does_not_stop_tenant_disable(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (503, None))

        result = self.stack.app.processor.handle(event("DELETE_ACCOUNT"))

        self.assertEqual(result.status, "dead_lettered")
        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_SET_ENABLED)), 1)
        self.assertEqual(len(self.stack.tenant2.calls("POST", fakes.TENANT_SET_ENABLED)), 1)

    def test_dead_letter_lists_every_failed_step(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_REMOVE_MEMBER, (403, None))
        self.stack.tenant.on("POST", fakes.TENANT_SET_ENABLED, (404, None))

        self.stack.app.processor.handle(event("DELETE_ACCOUNT"))

        (letter,) = self.stack.app.store.dead_letters()
        self.assertEqual(letter.error, "press.remove_team_member press: HTTP 403; tenant.set_enabled kiraci1: HTTP 404")
        self.assertEqual(len(self.stack.tenant2.calls("POST", fakes.TENANT_SET_ENABLED)), 1)


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

        closed = fakes.FakeSite()
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
        from identity_sync.mapping import digest_of
        from identity_sync.pipeline import replay_report

        return digest_of(replay_report(self.stack.app.processor.replay_dead_letters(dry_run=True)))

    def test_user_disabled_between_digest_check_and_execution_is_not_deprovisioned(self) -> None:
        # Onay "kullanıcıyı hazırla" planını gösterdi. Kullanıcı özet denetiminden hemen sonra kapatıldı.
        # Servis onaylanmayan yıkıcı planı yürütmemelidir.
        self.add_member()
        self.queue_failed()
        digest = self.digest()
        keycloak = self.stack.keycloak
        reads = {"count": 0}

        def user_route(_req: fakes.Recorded) -> fakes.Reply:
            reads["count"] += 1
            # 1. okuma: özet denetimi. 2. okuma: yürütme. Kullanıcı arada kapatıldı.
            return 200, keycloak_user(enabled=reads["count"] < 2)

        keycloak.on("GET", f"{keycloak.admin}/users/{SUBJECT}", user_route)
        writes = len(self.stack.press.writes() + self.stack.tenant.writes())

        results = self.stack.app.processor.replay_dead_letters(expected_digest=digest)

        self.assertEqual([r.status for _i, r in results], ["preview_changed"])
        self.assertEqual(len(self.stack.press.writes() + self.stack.tenant.writes()), writes)
        self.assertEqual(self.stack.press.calls("POST", fakes.PRESS_REMOVE_MEMBER), [])
        self.assertEqual(len(self.stack.app.store.dead_letters()), 1)

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

    def test_approved_replay_runs_the_previewed_plan(self) -> None:
        self.add_member()
        self.queue_failed()

        results = self.stack.app.processor.replay_dead_letters(expected_digest=self.digest())

        self.assertEqual([r.status for _i, r in results], ["processed"])


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

        last_write = tenant.writes()[-1]
        self.assertEqual(last_write.path, fakes.TENANT_SET_ENABLED)
        self.assertEqual(last_write.json()["enabled"], False)


class PreviewTest(PipelineCase):
    def test_dry_run_writes_nothing_and_remembers_nothing(self) -> None:
        self.add_member(enabled=False)

        result = self.stack.app.processor.handle(event("USER_UPDATE", "admin"), dry_run=True)

        self.assertEqual(result.status, "preview")
        self.assertEqual([p.operation for p in result.previews], ["press.remove_team_member", "tenant.set_enabled"])
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
