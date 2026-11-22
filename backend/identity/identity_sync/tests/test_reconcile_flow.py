"""Reconcile end to end: report, preview, approval and repair. Network calls go to the fake targets.

The fake targets follow the real target contracts. All users are made up.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event
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
                ("tenant.revoke_user_installations", True),
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


class MissedDeletionTest(ReconcileFlowCase):
    """An administrator deleted GONE in Keycloak and the event never arrived.

    docs/sozlesmeler.md, section 7: reconcile finds the deleted user and shows a preview. After
    the approval the remaining deletion steps run in order, even if the local account is closed.
    """

    GONE = "gone-1"

    def setUp(self) -> None:
        super().setUp()
        issuer = self.stack.issuer
        self.stack.press.seed_member(issuer, self.GONE, "gone@example.test", ORG_ID, api_keys=1)
        self.stack.tenant.seed_user(issuer, self.GONE, "gone@example.test", enabled=False)
        self.stack.press.users["gone@example.test"]["enabled"] = False
        self.job_id = self.stack.app.processor.account_job(self.GONE, time=1).id

    def gone_previews(self, report: dict) -> list[str]:
        return [p["operation"] for p in report["previews"] if self.job_id in p["summary"]]

    def test_deleted_user_with_closed_local_accounts_is_reported(self) -> None:
        plan = self.stack.app.reconcile_plan()

        self.assertIn(("press", self.GONE, "deleted_in_keycloak"), self.kinds(plan))
        self.assertIn(("kiraci1", self.GONE, "deleted_in_keycloak"), self.kinds(plan))
        self.assertEqual(
            self.gone_previews(plan.report()),
            [
                "press.remove_team_member",
                "tenant.set_enabled",
                "tenant.revoke_user_installations",
                "press.anonymize_user",
                "tenant.anonymize_user",
            ],
        )
        self.assertEqual(self.writes(), [])

    def test_approved_repair_runs_the_remaining_steps_in_order(self) -> None:
        issuer = self.stack.issuer
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]
        revoked_before_anonymize: list[int] = []

        def anonymize(_req: fakes.Recorded) -> fakes.Reply:
            revokes = self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)
            revoked_before_anonymize.append(sum(self.GONE in r.body.decode("utf-8") for r in revokes))
            return fakes.DONE

        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, anonymize)

        result = self.stack.app.reconcile_execute(digest)

        self.assertIn({"operation": "account_deletion", "target": self.job_id, "status": "done"}, result["results"])
        # Step 3 (installations) ran before step 4 (anonymize).
        self.assertEqual(revoked_before_anonymize, [1])
        self.assertTrue(self.stack.tenant.user_of(issuer, self.GONE)["anonymized"])
        self.assertTrue(self.stack.press.user_of(issuer, self.GONE)["anonymized"])
        # The drift is gone and the event, if it ever arrives, starts nothing.
        self.assertNotIn(self.GONE, [d.subject for d in self.stack.app.reconcile_plan().differences])
        late = Event(id="late-1", kind="admin", type="USER_DELETE", realm="platform", time=5, user_id=self.GONE)
        self.assertEqual(self.stack.app.processor.handle(late).status, "duplicate")

    def test_failed_step_stops_the_job_and_the_next_run_resumes(self) -> None:
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (503, None))
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]

        result = self.stack.app.reconcile_execute(digest)

        (job,) = [r for r in result["results"] if r["operation"] == "account_deletion"]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(self.stack.tenant.calls("POST", fakes.TENANT_ANONYMIZE), [])
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, fakes.DONE)
        # The next preview shows only what is left.
        report = self.stack.app.reconcile_plan().report()
        self.assertEqual(self.gone_previews(report), ["press.anonymize_user", "tenant.anonymize_user"])
        revokes = len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS))

        self.stack.app.reconcile_execute(report["preview_digest"])

        self.assertEqual(len(self.stack.tenant.calls("POST", fakes.TENANT_REVOKE_INSTALLATIONS)), revokes)
        self.assertTrue(self.stack.tenant.user_of(self.stack.issuer, self.GONE)["anonymized"])

    def test_approval_does_not_fit_when_the_remaining_steps_changed(self) -> None:
        # The human saw five steps. Meanwhile the late event ran three of them and stopped.
        # The differences are the same, but the work that is left is not what was approved.
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, (503, None))
        late = Event(id="late-2", kind="admin", type="USER_DELETE", realm="platform", time=5, user_id=self.GONE)
        self.assertEqual(self.stack.app.processor.handle(late).status, "dead_lettered")
        self.stack.press.on("POST", fakes.PRESS_ANONYMIZE, fakes.DONE)

        with self.assertRaises(PreviewChanged):
            self.stack.app.reconcile_execute(digest)
        self.assertFalse(self.stack.press.user_of(self.stack.issuer, self.GONE).get("anonymized"))

    def test_reply_names_the_deletion_job_not_the_account(self) -> None:
        # The account is deleted in Keycloak. Its raw id must not travel in a reply any more.
        import json

        plan = self.stack.app.reconcile_plan()
        report = plan.report()

        gone = [d for d in report["differences"] if d["kind"] == "deleted_in_keycloak"]
        self.assertEqual([(d["target"], d.get("job_id")) for d in gone], [("press", self.job_id), ("kiraci1", self.job_id)])
        self.assertTrue(all("subject" not in d for d in gone))
        self.assertNotIn(self.GONE, json.dumps(report))
        # Other kinds still name the user: the reader needs the id to act.
        self.assertIn(CLOSED, json.dumps(report))

        result = self.stack.app.reconcile_execute(report["preview_digest"])

        self.assertNotIn(self.GONE, json.dumps(result))
        self.assertIn(self.job_id, json.dumps(result))

    def test_preview_changes_when_a_deleted_account_appears(self) -> None:
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]
        self.stack.tenant.seed_user(self.stack.issuer, "gone-2", "gone2@example.test")

        with self.assertRaises(PreviewChanged):
            self.stack.app.reconcile_execute(digest)


class RepairTest(ReconcileFlowCase):
    def test_approved_repair_removes_the_drift(self) -> None:
        issuer = self.stack.issuer
        digest = self.stack.app.reconcile_plan().report()["preview_digest"]

        result = self.stack.app.reconcile_execute(digest)

        self.assertEqual([r["status"] for r in result["results"]], ["done"] * 6)
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



class PagedListTest(ReconcileFlowCase):
    """docs/sozlesmeler.md, section 7: `list_identities` is paged. The service reads every page
    and only then computes the differences."""

    def setUp(self) -> None:
        super().setUp()
        from identity_sync import sites

        original = sites.IDENTITY_PAGE_LENGTH
        sites.IDENTITY_PAGE_LENGTH = 2
        self.addCleanup(setattr, sites, "IDENTITY_PAGE_LENGTH", original)
        issuer = self.stack.issuer
        # The order is by subject. With pages of two, "zz-gone" and "zz-open" are on a later page.
        self.stack.keycloak.add_user(keycloak_user(subject="zz-open", email="zzopen@example.test"), [ORG])
        self.stack.keycloak.serve_directory()
        for subject in ("zz-gone", "zz-open"):
            self.stack.press.seed_member(issuer, subject, f"{subject}@example.test", ORG_ID)
            self.stack.tenant.seed_user(issuer, subject, f"{subject}@example.test")

    def test_deleted_and_open_accounts_on_the_second_page_are_both_seen(self) -> None:
        plan = self.stack.app.reconcile_plan()

        kinds = self.kinds(plan)
        # The deleted account on a later page is found on both targets.
        self.assertIn(("press", "zz-gone", "deleted_in_keycloak"), kinds)
        self.assertIn(("kiraci1", "zz-gone", "deleted_in_keycloak"), kinds)
        # The open account on a later page is known, so it is not reported as missing.
        self.assertEqual([kind for _target, subject, kind in kinds if subject == "zz-open"], [])
        for site, path in ((self.stack.press, fakes.PRESS_LIST), (self.stack.tenant, fakes.TENANT_LIST)):
            calls = site.calls("GET", path)
            self.assertEqual([c.query["start"] for c in calls], [["0"], ["2"], ["4"]][: len(calls)])
            self.assertGreaterEqual(len(calls), 2)
            self.assertEqual({c.query["page_length"][0] for c in calls}, {"2"})
            # GET with exactly these two query fields. No `cursor`, no `limit`, no body.
            self.assertEqual({frozenset(c.query) for c in calls}, {frozenset({"start", "page_length"})})
            self.assertEqual({c.body for c in calls}, {b""})

    def test_page_length_follows_the_contract(self) -> None:
        from identity_sync import sites

        self.addCleanup(setattr, sites, "IDENTITY_PAGE_LENGTH", 2)
        sites.IDENTITY_PAGE_LENGTH = 500
        self.stack.app.reconcile_plan()

        self.assertEqual(self.stack.press.calls("GET", fakes.PRESS_LIST)[0].query["page_length"], ["500"])

    def test_list_that_never_ends_is_an_error(self) -> None:
        from identity_sync.httpjson import TransportError

        endless = {"message": {"identities": [{"issuer": self.stack.issuer, "subject": "a", "enabled": True}], "has_next_page": True}}
        self.stack.press.on("GET", fakes.PRESS_LIST, (200, endless))

        with self.assertRaises(TransportError):
            self.stack.app.reconcile_plan()

    def test_reply_in_another_shape_is_an_error(self) -> None:
        from identity_sync.httpjson import TransportError

        for body in ([], {"identities": []}, {"identities": [], "has_next_page": "no"}, {"has_next_page": False}):
            with self.subTest(body=body):
                self.stack.press.on("GET", fakes.PRESS_LIST, (200, {"message": body}))
                with self.assertRaises(TransportError):
                    self.stack.app.reconcile_plan()
