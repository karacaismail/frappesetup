"""G-81 closure checks that join the separate pieces into one flow.

Each test follows one account from the Keycloak event to Press and the tenant. Then it compares
the result with the source account through the reconcile report. Network calls go to fake servers.
All users are made up.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event

from . import fakes
from .fakes import ORG_ID, SUBJECT, Stack, keycloak_user

ORG = {"id": ORG_ID, "name": "tenant1", "alias": "tenant1"}


def event(type_: str = "VERIFY_EMAIL", id_: str = "e-1", kind: str = "user") -> Event:
    return Event(id=id_, kind=kind, type=type_, realm="platform", time=1, user_id=SUBJECT)


class G81Case(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)

    def add_member(self, **overrides: object) -> None:
        self.stack.keycloak.add_user(keycloak_user(**overrides), [ORG])

    def drift(self) -> list[tuple[str, str, str]]:
        self.stack.keycloak.serve_directory()
        plan = self.stack.app.reconcile_plan()
        return [(d.target, d.subject, d.kind) for d in plan.differences]


class TransientRetryTest(G81Case):
    def test_transient_error_is_retried_and_the_event_is_processed(self) -> None:
        self.add_member()
        calls: list[int] = []

        def provision(_req: fakes.Recorded) -> fakes.Reply:
            calls.append(1)
            return (503, None) if len(calls) == 1 else fakes.DONE

        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, provision)

        result = self.stack.app.processor.handle(event())

        self.assertEqual(result.status, "processed")
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.stack.sleeps, [0.2])
        self.assertEqual(self.stack.app.store.dead_letters(), [])


class SourceComparisonTest(G81Case):
    def test_processed_member_matches_the_source_account(self) -> None:
        self.add_member()

        self.assertEqual(self.stack.app.processor.handle(event()).status, "processed")

        self.assertEqual(self.drift(), [])

    def test_disabled_account_matches_the_source_after_the_event(self) -> None:
        self.add_member()
        self.stack.app.processor.handle(event())
        self.stack.keycloak.add_user(keycloak_user(enabled=False), [ORG])

        self.assertEqual(self.stack.app.processor.handle(event("USER_UPDATE", "e-2", kind="admin")).status, "processed")

        self.assertEqual(self.drift(), [])
        self.assertFalse(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["enabled"])

    def test_email_change_matches_the_source_after_the_event(self) -> None:
        self.add_member()
        self.stack.app.processor.handle(event())
        self.stack.keycloak.add_user(keycloak_user(email="yeni@example.test"), [ORG])

        self.assertEqual(self.stack.app.processor.handle(event("UPDATE_EMAIL", "e-2")).status, "processed")

        self.assertEqual(self.drift(), [])
        self.assertEqual(self.stack.tenant.user_of(self.stack.issuer, SUBJECT)["email"], "yeni@example.test")

    def test_repeated_event_leaves_no_drift(self) -> None:
        self.add_member()

        self.stack.app.processor.handle(event())
        self.assertEqual(self.stack.app.processor.handle(event()).status, "duplicate")

        self.assertEqual(self.drift(), [])


class DeadLetterRecoveryTest(G81Case):
    def test_dead_letter_is_replayed_and_then_matches_the_source(self) -> None:
        self.add_member()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))

        self.assertEqual(self.stack.app.processor.handle(event()).status, "dead_lettered")
        self.assertIn(("tenant1", SUBJECT, "missing"), self.drift())

        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)
        results = self.stack.app.processor.replay_dead_letters()

        self.assertEqual([(event_id, r.status) for event_id, r in results], [("e-1", "processed")])
        self.assertEqual(self.stack.app.store.dead_letters(), [])
        self.assertEqual(self.drift(), [])


if __name__ == "__main__":
    unittest.main()
