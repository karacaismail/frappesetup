"""Reconcile end to end: report, preview, approval and repair. Network calls go to the fake targets.

The fake targets follow the real target contracts. All users are made up.
"""

from __future__ import annotations

import unittest

from identity_sync.pipeline import PreviewChanged

from . import fakes
from .fakes import ORG_ID, Stack, keycloak_user

ORG = {"id": ORG_ID, "name": "Kiracı 1", "alias": "kiraci1"}
MEMBER, CLOSED, NEWCOMER = "member-1", "closed-1", "newcomer-1"


class ReconcileFlowCase(unittest.TestCase):
    """Drift set up by hand:

    - MEMBER is in sync everywhere.
    - CLOSED is disabled in Keycloak but still enabled on Press and on the tenant.
    - NEWCOMER is an open member in Keycloak with no link on Press or on the tenant.
    """

    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)
        keycloak, issuer = self.stack.keycloak, self.stack.issuer
        keycloak.add_user(keycloak_user(subject=MEMBER, email="member@example.test"), [ORG])
        keycloak.add_user(keycloak_user(subject=CLOSED, email="closed@example.test", enabled=False), [ORG])
        keycloak.add_user(keycloak_user(subject=NEWCOMER, email="newcomer@example.test"), [ORG])
        keycloak.serve_directory()
        for subject, email in ((MEMBER, "member@example.test"), (CLOSED, "closed@example.test")):
            self.stack.press.seed_member(issuer, subject, email, ORG_ID, api_keys=1)
            self.stack.tenant.seed_user(issuer, subject, email)

    def writes(self) -> list[fakes.Recorded]:
        keycloak_writes = [r for r in self.stack.keycloak.requests if r.method != "GET" and "/admin/" in r.path]
        return self.stack.press.writes() + self.stack.tenant.writes() + keycloak_writes

    def kinds(self, plan) -> list[tuple[str, str, str]]:
        return [(d.target, d.subject, d.kind) for d in plan.differences]


class ReportTest(ReconcileFlowCase):
    def test_report_lists_the_drift_and_writes_nothing(self) -> None:
        plan = self.stack.app.reconcile_plan()

        self.assertEqual(
            self.kinds(plan),
            [
                ("press", CLOSED, "closed_in_keycloak"),
                ("press", NEWCOMER, "missing_team_membership"),
                ("kiraci1", CLOSED, "closed_in_keycloak"),
                ("kiraci1", NEWCOMER, "missing"),
            ],
        )
        self.assertEqual(self.writes(), [])

    def test_report_previews_the_repairs_without_personal_data(self) -> None:
        import json

        report = self.stack.app.reconcile_plan().report()

        self.assertEqual(report["count"], 4)
        self.assertEqual(
            [(p["operation"], p["destructive"]) for p in report["previews"]],
            [
                ("press.remove_team_member", True),
                ("press.ensure_team", False),
                ("tenant.set_enabled", True),
                ("tenant.change_email", False),
                ("tenant.provision", False),
            ],
        )
        self.assertRegex(report["preview_digest"], r"^[0-9a-f]{64}$")
        self.assertNotIn("example.test", json.dumps(report))

    def test_report_is_stable_while_nothing_changes(self) -> None:
        first = self.stack.app.reconcile_plan().report()
        second = self.stack.app.reconcile_plan().report()
        self.assertEqual(first, second)

    def test_no_drift_no_differences(self) -> None:
        stack = Stack()
        self.addCleanup(stack.close)
        stack.keycloak.serve_directory()

        report = stack.app.reconcile_plan().report()

        self.assertEqual((report["count"], report["differences"], report["previews"]), (0, [], []))


class RepairTest(ReconcileFlowCase):
    def test_approved_repair_removes_the_drift(self) -> None:
        issuer = self.stack.issuer
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]

        result = self.stack.app.reconcile_execute(digest)

        self.assertEqual([r["status"] for r in result["results"]], ["done"] * 5)
        closed_on_press = self.stack.press.user_of(issuer, CLOSED)
        self.assertEqual((closed_on_press["enabled"], closed_on_press["api_keys"]), (False, []))
        self.assertFalse(self.stack.tenant.user_of(issuer, CLOSED)["enabled"])
        self.assertEqual(self.stack.press.teams_of(issuer, NEWCOMER), [ORG_ID])
        self.assertTrue(self.stack.tenant.user_of(issuer, NEWCOMER)["enabled"])
        # The user that was in sync is untouched.
        self.assertTrue(self.stack.press.user_of(issuer, MEMBER)["enabled"])
        self.assertEqual(self.stack.app.reconcile_plan().report()["count"], 0)

    def test_repair_is_refused_when_the_drift_changed_after_the_preview(self) -> None:
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]
        self.stack.keycloak.add_user(keycloak_user(subject=MEMBER, email="member@example.test", enabled=False), [ORG])
        self.stack.keycloak.serve_directory()

        with self.assertRaises(PreviewChanged):
            self.stack.app.reconcile_execute(digest)
        self.assertEqual(self.writes(), [])

    def test_repair_is_refused_when_only_a_field_value_changed(self) -> None:
        # Same differences, same operations. Only the e-mail that would be written is new.
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]
        self.stack.keycloak.add_user(keycloak_user(subject=NEWCOMER, email="renamed@example.test"), [ORG])
        self.stack.keycloak.serve_directory()

        with self.assertRaises(PreviewChanged):
            self.stack.app.reconcile_execute(digest)
        self.assertEqual(self.writes(), [])

    def test_failed_and_unclear_repairs_are_reported_per_action(self) -> None:
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]
        self.stack.tenant.on("POST", fakes.TENANT_SET_ENABLED, (403, None))
        self.stack.press.on("POST", fakes.PRESS_ENSURE_TEAM, (202, {"message": {"status": "queued"}}))

        result = self.stack.app.reconcile_execute(digest)

        statuses = {(r["operation"], r["status"]) for r in result["results"]}
        self.assertIn(("tenant.set_enabled", "failed"), statuses)
        self.assertIn(("press.ensure_team", "unknown"), statuses)
        self.assertIn(("tenant.provision", "done"), statuses)
        # An unclear write is not repeated.
        self.assertEqual(len(self.stack.press.calls("POST", fakes.PRESS_ENSURE_TEAM)), 1)

    def test_repair_waits_for_a_running_event(self) -> None:
        import dataclasses

        from identity_sync.app import build_app
        from identity_sync.store import Busy

        # A second process holds the work lock. The repair does not run beside it.
        import os
        import tempfile

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = dataclasses.replace(
            self.stack.settings, db_path=os.path.join(directory.name, "db.sqlite3"), lock_timeout=0.2
        )
        first, second = build_app(settings), build_app(settings)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        digest = first.reconcile_plan().report()["preview_digest"]

        with second.store.work_lock():
            with self.assertRaises(Busy):
                first.reconcile_execute(digest)
        self.assertEqual(self.writes(), [])


if __name__ == "__main__":
    unittest.main()
