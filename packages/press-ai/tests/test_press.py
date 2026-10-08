"""Press tarafı: istemci, okuma projeksiyonu, ön koşullar, onaylı yürütme, izleme ve güvenlik sınırları.

Senaryolar pressguide@2b83441 kılavuz adımlarından türetilmiştir (adım kimlikleri test adlarında/yorumlarda);
sahte Press yalnız frappe/press @ebf3e22 dönüş biçimlerini taklit eder. Canlı Press çağrısı yoktur.
"""
import datetime as dt
import json
import unittest

import fake_press
import support
from press_ai import press_ops
from press_ai.errors import ApprovalError, ConfigError, KitError, PreconditionError, PressError, ValidationError
from press_ai.press_client import PressClient
from press_ai.tools import Context
from support import PressCase, approve, make_config

ALL_MUTATIONS = tuple(press_ops.MUTATIONS)
SUCCESS_STEPS = [{"stage": "Clone Repositories", "step": s, "stage_slug": "clone", "step_slug": s, "status": "Success",
                  "output": "ok"} for s in ("frappe", "erpnext")] + [
    {"stage": "Upload", "step": "Docker Image", "stage_slug": "upload", "step_slug": "image", "status": "Success",
     "output": "pushed"}]


class TeamReads(PressCase):
    PRINCIPAL = "team"

    def test_every_request_carries_configured_team_and_token(self):
        self.call("press_read", operation="release_group.get", params={"release_group": "bench-0042"})
        for _, _, headers in self.fake.requests:
            self.assertEqual(headers.get("X-Press-Team"), "team-alpha")
            self.assertTrue(headers.get("Authorization").startswith("token "))

    def test_site_get_drops_personal_data(self):
        out = self.call("press_read", operation="site.get", params={"site": "school.example.test"})
        text = json.dumps(out)
        self.assertNotIn("owner@example.test", text)
        self.assertEqual(out["result"]["untrusted_data"]["site"]["status"], "Active")

    def test_backups_drop_signed_urls(self):
        out = self.call("press_read", operation="site.backups", params={"site": "school.example.test"})
        self.assertNotIn("signed?token", json.dumps(out))

    def test_other_teams_site_is_refused_by_press(self):
        self.fake.sites["school.example.test"]["team"] = "team-beta"
        with self.assertRaises(PressError) as caught:
            self.call("press_read", operation="site.get", params={"site": "school.example.test"})
        self.assertEqual(caught.exception.kind, "permission")

    def test_unknown_or_mutating_operation_is_not_a_read(self):
        with self.assertRaises(KitError) as caught:
            self.call("press_read", operation="site.migrate", params={"site": "school.example.test"})
        self.assertEqual(caught.exception.code, "not_a_read")
        with self.assertRaises(KitError):
            self.call("press_read", operation="server.reboot", params={})

    def test_operator_only_reads_refuse_team_principal(self):
        with self.assertRaises(ConfigError) as caught:
            self.call("press_read", operation="error_log.list", params={})
        self.assertEqual(caught.exception.code, "wrong_principal")

    def test_params_are_validated(self):
        with self.assertRaises(ValidationError):
            self.call("press_read", operation="site.get", params={"site": "../../etc"})
        with self.assertRaises(ValidationError):
            self.call("press_read", operation="site.get", params={"site": "school.example.test", "team": "team-beta"})


class ClientBehaviour(PressCase):
    def client(self):
        return self.ctx.press()

    def test_error_bodies_are_redacted_and_mapped(self):
        self.fake.fail["press.api.bench.get"] = (417, "ValidationError",
                                                 "bad value token abcdef123456:zyx987654321 api_secret=topsecret99")
        with self.assertRaises(PressError) as caught:
            self.client().call("press.api.bench.get", {"name": "bench-0042"})
        self.assertEqual(caught.exception.kind, "validation")
        self.assertNotIn("zyx987654321", str(caught.exception))
        self.assertNotIn("topsecret99", str(caught.exception))

    def test_redirects_are_refused(self):
        with self.assertRaises(PressError):
            self.client()._request("/redirect", {}, "POST")

    def test_timeout_is_unknown(self):
        _, config = make_config(self.home, self.server.url, timeout=1)
        ctx = Context(config, clock=self.clock)
        self.fake.delay["press.api.bench.get"] = 2
        from press_ai.errors import PressTimeout
        with self.assertRaises(PressTimeout):
            ctx.press().call("press.api.bench.get", {"name": "bench-0042"})

    def test_bad_credentials(self):
        from press_ai.credentials import Credentials
        client = PressClient(self.config.press, Credentials("wrongkey1", "wrongsecret1", "test"), self.ctx.redactor)
        with self.assertRaises(PressError) as caught:
            client.call("frappe.auth.get_logged_user")
        self.assertEqual(caught.exception.kind, "authentication")


class OperatorReads(PressCase):
    PRINCIPAL = "operator"
    TEAM = "team-alpha"

    def setUp(self):
        super().setUp()
        self.candidate = self.fake.make_candidate("bench-0042")
        self.build = self.fake.make_build(self.candidate, "Failure", [
            {"stage": "Pre-build", "step": "Validate dependencies", "stage_slug": "validate", "step_slug": "deps",
             "status": "Failure", "output": "Required app not found: erpnext (needed by education)"},
            {"stage": "Upload", "step": "Docker Image", "stage_slug": "upload", "step_slug": "image",
             "status": "Pending", "output": ""}])
        self.job = self.fake.add_job("Run Remote Builder", "Failure", reference=("Deploy Candidate Build", self.build),
                                     output="registry_password=hunter2-very-secret failed")

    def requested_fields(self):
        fields = []
        for method, args, _ in self.fake.requests:
            if method == "frappe.client.get_list":
                fields.extend(args["fields"])
        return fields

    def test_never_reads_full_documents_or_secret_fields(self):
        self.call("press_read", operation="deploy_candidate.get", params={"deploy_candidate": self.candidate})
        self.call("press_read", operation="build.get", params={"build": self.build})
        self.call("press_read", operation="agent_job.get", params={"job": self.job})
        self.call("press_read", operation="press_settings.flags", params={})
        self.assertNotIn("frappe.client.get", self.methods())
        self.assertFalse(set(self.requested_fields()) & fake_press.SECRET_FIELDS)
        settings_args = [a for m, a, _ in self.fake.requests if m == "frappe.client.get_value"][0]
        self.assertNotIn("github_access_token", settings_args["fieldname"])

    def test_outputs_contain_no_secrets(self):
        outputs = [
            self.call("press_read", operation="deploy_candidate.get", params={"deploy_candidate": self.candidate}),
            self.call("press_read", operation="agent_job.get", params={"job": self.job}),
            self.call("press_read", operation="press_settings.flags", params={}),
        ]
        text = json.dumps(outputs)
        for secret in ("PRIVATE KEY", "bt-secret-0001", "hunter2-very-secret", fake_press.FAKE_GITHUB_TOKEN, support.SECRET):
            self.assertNotIn(secret, text)

    def test_triage_reports_first_failure_and_ignores_pending(self):
        out = self.call("press_triage_build", build=self.build)["result"]["untrusted_data"]
        self.assertEqual(out["classification"], "required_app_not_found")
        self.assertEqual(out["first_failure"]["stage"], "Pre-build")
        self.assertEqual(out["pending_after_first_failure"], 1)
        self.assertIn("live-error", out["guide_steps"])

    def test_candidate_list_derives_status_from_builds(self):
        out = self.call("press_read", operation="deploy_candidate.list", params={"release_group": "bench-0042"})
        rows = out["result"]["untrusted_data"]["candidates"]
        self.assertEqual(rows[0]["latest_build"]["status"], "Failure")


class OperatorFlow(PressCase):
    """Kılavuz akışı: candidate (`candidate`) → yalnız build (`schedule`, `live-build-complete`) → Success
    (`live-build-success`) → ayrı deploy → Bench Active (`live-bench-active`)."""

    PRINCIPAL = "operator"
    MUTATIONS = ("deploy_candidate.create", "build.start", "deploy.start", "release_group.add_app",
                 "app_release.create")

    def propose_and_approve(self, operation, **params):
        proposal = self.call("press_propose", operation=operation, params=params)
        self.assertEqual(proposal["state"], "pending")
        approve(self.ctx, proposal["proposal_id"])
        return proposal

    def test_full_build_then_separate_deploy(self):
        created = self.propose_and_approve("deploy_candidate.create", release_group="bench-0042")
        out = self.call("press_execute", proposal_id=created["proposal_id"])
        self.assertEqual(out["state"], "accepted")
        tracked = self.call("press_track", proposal_id=created["proposal_id"])
        self.assertEqual(tracked["state"], "succeeded")
        candidate = tracked["untrusted_data"]["evidence"]["candidate"]

        build_p = self.propose_and_approve("build.start", deploy_candidate=candidate)
        self.assertEqual(build_p["request"], {"transport": "doc_method", "doctype": "Deploy Candidate",
                                              "name": candidate, "method": "build", "args": {"no_cache": False}})
        executed = self.call("press_execute", proposal_id=build_p["proposal_id"])
        self.assertEqual(executed["state"], "accepted")
        build = executed["untrusted_data"]["references"]["created"]
        self.assertEqual(self.call("press_track", proposal_id=build_p["proposal_id"])["state"], "in_progress")

        # Build bitmeden deploy önerisi reddedilir.
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="deploy.start", params={"build": build})
        failed = [c for c in caught.exception.details["checks"] if c["ok"] is not True]
        self.assertEqual(failed[0]["id"], "build.success_all_steps")

        self.fake.builds[build].update(status="Success", build_steps=SUCCESS_STEPS)
        self.assertEqual(self.call("press_track", proposal_id=build_p["proposal_id"])["state"], "succeeded")

        deploy_p = self.call("press_propose", operation="deploy.start", params={"build": build})
        self.assertEqual(deploy_p["approval_level"], "double")
        self.assertIn("active_sites_in_group", deploy_p["preview"]["untrusted_data"]["impact"])
        approve(self.ctx, deploy_p["proposal_id"])
        executed = self.call("press_execute", proposal_id=deploy_p["proposal_id"])
        self.assertEqual(executed["state"], "accepted")
        self.assertEqual(self.call("press_track", proposal_id=deploy_p["proposal_id"])["state"], "in_progress")
        for bench in self.fake.benches.values():
            if bench["candidate"] == candidate:
                bench["status"] = "Active"
        for job in self.fake.jobs.values():
            if job["job_type"] == "New Bench":
                job["status"] = "Success"
        final = self.call("press_track", proposal_id=deploy_p["proposal_id"])
        self.assertEqual(final["state"], "succeeded")
        self.assertIn("not site success", final["untrusted_data"]["evidence"]["note"])

    def test_status_success_with_a_failed_step_is_not_deployable(self):
        candidate = self.fake.make_candidate("bench-0042")
        steps = [dict(s) for s in SUCCESS_STEPS]
        steps[-1]["status"] = "Failure"
        build = self.fake.make_build(candidate, "Success", steps)
        with self.assertRaises(PreconditionError):
            self.call("press_propose", operation="deploy.start", params={"build": build})

    def test_existing_deploy_for_candidate_blocks_second_deploy(self):
        candidate = self.fake.make_candidate("bench-0042")
        build = self.fake.make_build(candidate, "Success", SUCCESS_STEPS)
        self.fake.deploys["dpl-old"] = {"name": "dpl-old", "group": "bench-0042", "candidate": candidate,
                                        "creation": "now"}
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="deploy.start", params={"build": build})
        ids = [c["id"] for c in caught.exception.details["checks"] if c["ok"] is not True]
        self.assertEqual(ids, ["deploy.not_created_for_candidate"])

    def test_build_refused_without_releases_or_with_active_build(self):
        bare = self.fake.make_candidate("bench-0042", released=False)
        with self.assertRaises(PreconditionError):
            self.call("press_propose", operation="build.start", params={"deploy_candidate": bare})
        busy = self.fake.make_candidate("bench-0042")
        self.fake.make_build(busy, "Running")
        with self.assertRaises(PreconditionError):
            self.call("press_propose", operation="build.start", params={"deploy_candidate": busy})

    def test_preconditions_are_rechecked_at_execution(self):
        candidate = self.fake.make_candidate("bench-0042")
        proposal = self.propose_and_approve("build.start", deploy_candidate=candidate)
        self.fake.make_build(candidate, "Running")  # Onaydan sonra başka biri build başlattı.
        with self.assertRaises(PreconditionError):
            self.call("press_execute", proposal_id=proposal["proposal_id"])
        # Onay tüketilmedi: durum değişince insan yeni öneriye karar verir.
        self.assertEqual(self.ctx.store.status(proposal["proposal_id"])["state"], "approved")

    def test_add_app_checks_source_and_absence(self):
        with self.assertRaises(PreconditionError):
            self.call("press_propose", operation="release_group.add_app",
                      params={"release_group": "bench-0042", "app": "erpnext", "source": "SRC-payments-1"})
        proposal = self.propose_and_approve("release_group.add_app", release_group="bench-0042", app="erpnext",
                                            source="SRC-erpnext-1")
        self.assertEqual(self.call("press_execute", proposal_id=proposal["proposal_id"])["state"], "accepted")
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "succeeded")

    def test_release_refused_when_auto_deploy_is_on(self):
        self.fake.group_apps["bench-0042"][1]["enable_auto_deploy"] = 1
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="app_release.create",
                      params={"release_group": "bench-0042", "app": "payments"})
        self.assertIn("release_group.auto_deploy_off",
                      [c["id"] for c in caught.exception.details["checks"] if c["ok"] is not True])

    def test_timeout_is_unknown_and_blocks_blind_retry(self):
        candidate = self.fake.make_candidate("bench-0042")
        proposal = self.propose_and_approve("build.start", deploy_candidate=candidate)
        self.ctx.press().config.timeout = 1
        self.fake.delay["run_doc_method"] = 2
        out = self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertEqual(out["state"], "unknown")
        self.fake.delay.clear()
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="build.start", params={"deploy_candidate": candidate})
        self.assertIn("proposal.no_unknown_outcome",
                      [c["id"] for c in caught.exception.details["checks"] if c["ok"] is not True])

    def test_press_validation_error_is_rejected_not_unknown(self):
        candidate = self.fake.make_candidate("bench-0042")
        proposal = self.propose_and_approve("build.start", deploy_candidate=candidate)
        self.fake.fail["run_doc_method"] = (417, "ValidationError", "Deployments on this server are halted")
        out = self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertEqual(out["state"], "rejected_by_press")

    def test_only_three_doc_methods_are_reachable(self):
        doc_methods = set()
        sample = {"release_group": "g", "deploy_candidate": "c", "build": "b", "site": "s.example.test", "app": "a",
                  "source": "x", "title": "t", "version": "v", "cluster": "c", "apps": [{"app": "a", "source": "s"}]}
        for mutation in press_ops.MUTATIONS.values():
            request = mutation.request(sample)
            if request["transport"] == "doc_method":
                doc_methods.add((request["doctype"], request["method"]))
            else:
                self.assertTrue(request["method"].startswith("press.api."), request)
        self.assertEqual(doc_methods, {("Release Group", "create_deploy_candidate"), ("Deploy Candidate", "build"),
                                       ("Deploy Candidate Build", "deploy")})


class TeamSiteFlow(PressCase):
    """Site işleri: iş adı dönmez, iş listesi farkıyla izlenir; kurulu uygulama no_op olur."""

    PRINCIPAL = "team"
    MUTATIONS = ("site.backup", "site.migrate", "site.install_app")

    def test_disabled_mutation_needs_human_config(self):
        _, config = make_config(self.home, self.server.url, mutations=())
        ctx = Context(config, clock=self.clock)
        from press_ai.tools import Toolbox
        with self.assertRaises(ConfigError) as caught:
            Toolbox(ctx).call("press_propose", {"operation": "site.backup", "params": {"site": "school.example.test"}})
        self.assertEqual(caught.exception.code, "mutation_disabled")

    def test_operator_only_mutation_refuses_team(self):
        _, config = make_config(self.home, self.server.url, mutations=("build.start",))
        from press_ai.tools import Toolbox
        with self.assertRaises(ConfigError) as caught:
            Toolbox(Context(config)).call("press_propose", {"operation": "build.start",
                                                            "params": {"deploy_candidate": "c"}})
        self.assertEqual(caught.exception.code, "wrong_principal")

    def test_backup_then_migrate_with_recent_backup(self):
        # Eski yedek: migrate önerisi engellenir.
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="site.migrate", params={"site": "school.example.test"})
        self.assertIn("site.recent_backup", [c["id"] for c in caught.exception.details["checks"] if c["ok"] is not True])
        backup = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        approve(self.ctx, backup["proposal_id"])
        self.assertEqual(self.call("press_execute", proposal_id=backup["proposal_id"])["state"], "accepted")
        self.assertEqual(self.call("press_track", proposal_id=backup["proposal_id"])["state"], "in_progress")
        job = [j for j in self.fake.jobs.values() if j["job_type"] == "Backup Site"][0]
        job["status"] = "Success"
        self.assertEqual(self.call("press_track", proposal_id=backup["proposal_id"])["state"], "succeeded")
        self.fake.backups["school.example.test"].insert(0, {"name": "BKP-2", "creation": "2026-10-08 15:05:00.000000",
                                                           "status": "Success", "with_files": 0, "offsite": 0})
        migrate = self.call("press_propose", operation="site.migrate", params={"site": "school.example.test"})
        self.assertEqual(migrate["approval_level"], "double")
        record = self.ctx.store.load(migrate["proposal_id"])
        self.assertEqual(record["confirm_phrase"], "MIGRATE school.example.test")

    def test_install_app_already_installed_is_no_op(self):
        self.fake.backups["school.example.test"].insert(0, {"name": "BKP-3", "creation": "2026-10-08 15:00:00",
                                                           "status": "Success"})
        with self.assertRaises(PreconditionError):
            self.call("press_propose", operation="site.install_app",
                      params={"site": "school.example.test", "app": "payments"})
        proposal = self.call("press_propose", operation="site.install_app",
                             params={"site": "school.example.test", "app": "erpnext"})
        approve(self.ctx, proposal["proposal_id"])
        self.fake.sites["school.example.test"]["apps"].append("erpnext")  # onaydan sonra başka biri kurdu
        with self.assertRaises(PreconditionError):
            self.call("press_execute", proposal_id=proposal["proposal_id"])

    def test_install_job_tracked_to_success_or_unknown(self):
        self.fake.backups["school.example.test"].insert(0, {"name": "BKP-4", "creation": "2026-10-08 15:00:00",
                                                           "status": "Success"})
        proposal = self.call("press_propose", operation="site.install_app",
                             params={"site": "school.example.test", "app": "erpnext"})
        approve(self.ctx, proposal["proposal_id"])
        self.fake.jobs.clear()
        original = self.fake.m_press__api__site__install_app
        self.fake.m_press__api__site__install_app = lambda a: fake_press.ok(None)  # Press iş açmadan döndü
        try:
            self.assertEqual(self.call("press_execute", proposal_id=proposal["proposal_id"])["state"], "accepted")
        finally:
            self.fake.m_press__api__site__install_app = original
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "in_progress")
        self.clock.advance(minutes=11)
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "unknown")

    def test_secret_never_lands_in_state_files(self):
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        approve(self.ctx, proposal["proposal_id"])
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.call("press_track", proposal_id=proposal["proposal_id"])
        self.assertNotIn(support.SECRET, self.state_text())
        self.assertNotIn(support.KEY, self.state_text())

    def test_proposal_for_other_authority_is_refused(self):
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        approve(self.ctx, proposal["proposal_id"])
        _, other = make_config(self.home, self.server.url, team="team-beta", mutations=self.MUTATIONS)
        from press_ai.tools import Toolbox
        with self.assertRaises(ApprovalError) as caught:
            Toolbox(Context(other, clock=self.clock)).call("press_execute", {"proposal_id": proposal["proposal_id"]})
        self.assertEqual(caught.exception.code, "authority_changed")


def _failed_ids(error):
    return [c["id"] for c in error.details["checks"] if c["ok"] is not True]


def _untrusted(value):
    """press_propose önizlemesi, press_track kanıtı ve press_execute yanıtı güvenilmeyen veri zarfındadır."""
    return value["untrusted_data"]


class OperatorSourceAligned(PressCase):
    """review-final M3, M4, M6, M7, m13: sahte Press frappe/press @ebf3e22 davranışına hizalı."""

    PRINCIPAL = "operator"
    MUTATIONS = ("deploy_candidate.create", "build.start", "deploy.start", "app_release.create")

    def successful_build(self, group="bench-0042"):
        candidate = self.fake.make_candidate(group)
        return candidate, self.fake.make_build(candidate, "Success", [dict(x) for x in SUCCESS_STEPS])

    def test_m3_running_build_without_pipeline_blocks_new_candidate(self):
        # bench.py deploy_status yalnız Release Pipeline'a bakar; Desk build'i pipeline açmaz.
        candidate = self.fake.make_candidate("bench-0042")
        self.fake.make_build(candidate, "Running")
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="deploy_candidate.create", params={"release_group": "bench-0042"})
        self.assertIn("release_group.no_deploy_in_progress", _failed_ids(caught.exception))

    def test_m3_deploy_status_reads_deploy_information(self):
        candidate = self.fake.make_candidate("bench-0042")
        self.fake.make_build(candidate, "Preparing")
        out = _untrusted(self.call("press_read", operation="deploy.status",
                                   params={"release_group": "bench-0042"})["result"])
        self.assertTrue(out["busy"])
        self.assertTrue(out["deploy_in_progress"])
        self.assertEqual(out["last_deploy"]["status"], "Preparing")

    def test_m4_multi_server_deploy_waits_for_every_server(self):
        self.fake.group_servers["bench-0042"] = ["f1-app.example.test", "f2-app.example.test"]
        self.fake.auto_start_benches = False
        _, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        approve(self.ctx, proposal["proposal_id"])
        self.assertEqual(self.call("press_execute", proposal_id=proposal["proposal_id"])["state"], "accepted")
        deploy = list(self.fake.deploys)[-1]
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "in_progress")
        self.fake.start_bench(deploy, "f1-app.example.test", status="Active", job_status="Success")
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "in_progress")
        self.fake.start_bench(deploy, "f2-app.example.test", status="Active", job_status="Success")
        final = self.call("press_track", proposal_id=proposal["proposal_id"])
        self.assertEqual(final["state"], "succeeded")
        servers = {b["server"] for b in _untrusted(final)["evidence"]["benches"]}
        self.assertEqual(servers, {"f1-app.example.test", "f2-app.example.test"})

    def test_m6_other_group_with_auto_deploy_on_same_source_blocks_release(self):
        self.fake.groups["bench-0043"] = dict(self.fake.groups["bench-0042"], name="bench-0043", title="other")
        self.fake.group_apps["bench-0043"] = [{"app": "payments", "source": "SRC-payments-1", "enable_auto_deploy": 1}]
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="app_release.create",
                      params={"release_group": "bench-0042", "app": "payments"})
        self.assertIn("release_group.auto_deploy_off", _failed_ids(caught.exception))

    def test_m6_deploy_marker_makes_release_unverifiable(self):
        # <işaret>-<grup> etiketsiz grubu da dağıtır; commit mesajı önceden bilinmez → None (engel).
        self.fake.settings["deploy_marker"] = "[deploy]"
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="app_release.create",
                      params={"release_group": "bench-0042", "app": "payments"})
        self.assertIn("release_group.auto_deploy_off", _failed_ids(caught.exception))

    def test_m6_failed_github_poll_is_failed_not_no_op(self):
        proposal = self.call("press_propose", operation="app_release.create",
                             params={"release_group": "bench-0042", "app": "payments"})
        approve(self.ctx, proposal["proposal_id"])
        self.fake.m_press__api__bench__fetch_latest_app_update = lambda a: fake_press.ok(None)  # hata yutuldu
        self.fake.group_apps["bench-0042"][1]["last_github_poll_failed"] = 1
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.clock.advance(minutes=3)
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "failed")

    def test_m7_deploy_preview_names_sites_that_press_auto_updates(self):
        _, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        impact = _untrusted(proposal["preview"])["impact"]
        sites = {s["name"]: s for s in impact["sites_in_group"]}
        self.assertTrue(sites["school.example.test"]["auto_updates_enabled"])
        self.assertIn("auto", impact["site_auto_updates"].lower())
        record = self.ctx.store.load(proposal["proposal_id"])
        self.assertIn("AUTO-UPDATE", record["confirm_phrase"])

    def test_deploy_refused_when_candidate_points_to_another_build(self):
        # Press imajı candidate.intel_build/arm_build'den alır (deploy.py _get_build_for_bench), çağrılandan değil.
        candidate, older = self.successful_build()
        self.fake.make_build(candidate, "Success", [dict(x) for x in SUCCESS_STEPS])  # daha yeni başarılı build
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="deploy.start", params={"build": older})
        self.assertIn("deploy.artifact_matches_build", _failed_ids(caught.exception))

    def test_artifact_change_after_approval_blocks_execution(self):
        candidate, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        artifact = _untrusted(proposal["preview"])["impact"]["artifact"]
        self.assertEqual(artifact["build"], build)
        self.assertTrue(artifact["docker_image"].endswith(build))
        self.assertEqual({v["deploys_build"] for v in artifact["servers"].values()}, {build})
        approve(self.ctx, proposal["proposal_id"])
        self.fake.make_build(candidate, "Success", [dict(x) for x in SUCCESS_STEPS])  # onaydan sonra yeni imaj
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertIn("deploy.artifact_matches_build", _failed_ids(caught.exception))
        self.assertEqual(self.fake.deploys, {})

    def test_r_busy_while_bench_creation_is_queued_or_installing(self):
        # Press deploy_in_progress bench kurulumunu görmez (last_benches_info build adıyla arar).
        self.fake.auto_start_benches = False
        _, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        approve(self.ctx, proposal["proposal_id"])
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        with self.assertRaises(PreconditionError) as caught:  # kuyruk Queued
            self.call("press_propose", operation="deploy_candidate.create", params={"release_group": "bench-0042"})
        self.assertIn("release_group.no_deploy_in_progress", _failed_ids(caught.exception))
        deploy = list(self.fake.deploys)[-1]
        bench = self.fake.start_bench(deploy, "f1-app.example.test", status="Installing")
        with self.assertRaises(PreconditionError):  # bench Installing
            self.call("press_propose", operation="deploy_candidate.create", params={"release_group": "bench-0042"})
        self.assertTrue(_untrusted(self.call("press_read", operation="deploy.status",
                                             params={"release_group": "bench-0042"})["result"])["busy"])
        self.fake.benches[bench]["status"] = "Active"
        created = self.call("press_propose", operation="deploy_candidate.create", params={"release_group": "bench-0042"})
        self.assertEqual(created["state"], "pending")

    def test_r_auto_update_set_follows_scheduler(self):
        base = self.fake.sites["school.example.test"]
        for name, status, skip, fatal in (("inactive.example.test", "Inactive", 0, None),
                                          ("broken.example.test", "Broken", 0, None),
                                          ("manual.example.test", "Active", 1, None),
                                          ("fatal.example.test", "Suspended", 0, "SU-1")):
            self.fake.sites[name] = dict(base, name=name, host_name=name, status=status, skip_auto_updates=skip,
                                         fatal_site_update=fatal)
        _, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        artifact = _untrusted(proposal["preview"])["impact"]["artifact"]
        self.assertEqual(artifact["auto_update_sites"], ["inactive.example.test", "school.example.test"])
        record = self.ctx.store.load(proposal["proposal_id"])
        self.assertEqual(record["confirm_phrase"], "DEPLOY {} AUTO-UPDATE 2".format(build))
        approve(self.ctx, proposal["proposal_id"])
        self.fake.sites["manual.example.test"]["skip_auto_updates"] = 0  # onaydan sonra etki alanı büyüdü
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertIn("deploy.artifact_matches_build", _failed_ids(caught.exception))

    def test_r_mixed_platform_group_is_refused(self):
        self.fake.group_servers["bench-0042"] = ["f1-app.example.test", "f9-app.example.test"]  # x86_64 + arm64
        _, build = self.successful_build()
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="deploy.start", params={"build": build})
        self.assertIn("deploy.artifact_matches_build", _failed_ids(caught.exception))

    def test_r_deploy_tracker_ignores_foreign_bench_and_checks_built_artifact(self):
        self.fake.auto_start_benches = False
        candidate, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        approve(self.ctx, proposal["proposal_id"])
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.fake.benches["foreign"] = {"name": "foreign", "group": "bench-0042", "status": "Active",
                                        "server": "f1-app.example.test", "candidate": candidate, "build": build}
        self.fake.add_job("New Bench", "Success", bench="foreign")
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "in_progress")
        deploy = list(self.fake.deploys)[-1]
        queue = self.fake.deploys[deploy]["benches"][0]["bench"]
        self.fake.queues[queue]["build"] = "bld-other"  # Press başka bir imajı sabitledi
        self.fake.start_bench(deploy, "f1-app.example.test", status="Active", job_status="Success")
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "failed")

    def test_r_queue_failure_is_failed(self):
        self.fake.auto_start_benches = False
        _, build = self.successful_build()
        proposal = self.call("press_propose", operation="deploy.start", params={"build": build})
        approve(self.ctx, proposal["proposal_id"])
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        for queue in self.fake.queues.values():
            queue["status"] = "Failure"
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "failed")

    def test_r_swallowed_create_release_error_is_failed(self):
        proposal = self.call("press_propose", operation="app_release.create",
                             params={"release_group": "bench-0042", "app": "payments"})
        approve(self.ctx, proposal["proposal_id"])
        self.fake.m_press__api__bench__fetch_latest_app_update = lambda a: fake_press.ok(None)
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.fake.error_logs.append({"name": "ERR-77", "method": "Create Release Error", "creation": "now",
                                     "reference_doctype": "App Source", "reference_name": "SRC-payments-1"})
        self.clock.advance(minutes=3)
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "failed")

    def test_r_consumed_without_outcome_is_not_sent_and_not_probed(self):
        candidate = self.fake.make_candidate("bench-0042")
        proposal = self.call("press_propose", operation="build.start", params={"deploy_candidate": candidate})
        approve(self.ctx, proposal["proposal_id"])
        self.ctx.store.consume(proposal["proposal_id"])  # süreç gönderimden önce öldü
        before = len(self.fake.requests)
        tracked = self.call("press_track", proposal_id=proposal["proposal_id"])
        self.assertEqual((tracked["state"], tracked["phase"]), ("unknown", "not_sent"))
        self.assertEqual(len(self.fake.requests), before)
        self.assertTrue(self.ctx.store.unresolved("build.start", candidate))

    def test_m13_operator_lists_are_scoped_to_configured_team(self):
        groups = _untrusted(self.call("press_read", operation="release_group.list", params={})["result"])
        self.assertTrue(groups and all(g["team"] == "team-alpha" for g in groups))
        servers = _untrusted(self.call("press_read", operation="server.list", params={})["result"])
        self.assertTrue(servers and all(s["team"] == "team-alpha" for s in servers))
        self.assertNotIn("f9-app.example.test", [s["name"] for s in servers])


class TeamSourceAligned(PressCase):
    """review-final M5, M8, M9, m4, m8 (team principal)."""

    PRINCIPAL = "team"
    MUTATIONS = ("release_group.add_app", "release_group.create", "site.backup", "site.install_app")

    def test_m5_public_marketplace_source_is_verified_for_team(self):
        # installable_apps/options yalnız çerçeve kaynaklarını döndürür; doğrulama all_apps ile yapılır.
        proposal = self.call("press_propose", operation="release_group.add_app",
                             params={"release_group": "bench-0042", "app": "erpnext", "source": "SRC-erpnext-1"})
        self.assertEqual(proposal["state"], "pending")
        self.fake.sources["SRC-erpnext-1"]["public"] = 0
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="release_group.add_app",
                      params={"release_group": "bench-0042", "app": "erpnext", "source": "SRC-erpnext-1"})
        self.assertIn("app_source.matches_app", _failed_ids(caught.exception))

    def test_m5_create_verifies_only_framework_sources(self):
        ok = self.call("press_propose", operation="release_group.create",
                       params={"title": "new-school", "version": "Version 16", "cluster": "Default",
                               "apps": [{"app": "frappe", "source": "SRC-frappe-1"}]})
        self.assertEqual(ok["state"], "pending")
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="release_group.create",
                      params={"title": "new-school-2", "version": "Version 16", "cluster": "Default",
                              "apps": [{"app": "frappe", "source": "SRC-frappe-1"},
                                       {"app": "erpnext", "source": "SRC-erpnext-1"}]})
        self.assertIn("app_source.matches_app", _failed_ids(caught.exception))

    def test_m8_install_app_never_sends_a_marketplace_plan(self):
        self.fake.backups["school.example.test"].insert(0, {"name": "BKP-9", "creation": "2026-10-08 15:00:00",
                                                           "status": "Success"})
        with self.assertRaises(ValidationError):
            self.call("press_propose", operation="site.install_app",
                      params={"site": "school.example.test", "app": "erpnext", "plan": "erpnext-pro"})
        proposal = self.call("press_propose", operation="site.install_app",
                             params={"site": "school.example.test", "app": "erpnext"})
        self.assertIsNone(proposal["request"]["args"]["plan"])
        approve(self.ctx, proposal["proposal_id"])
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertEqual(self.fake.subscriptions, [])

    def test_m9_silent_team_fallback_is_detected(self):
        self.fake.member_teams = {"team-beta"}
        self.fake.default_team = "team-beta"  # yapılandırılan team-alpha'ya üyelik yok
        context = _untrusted(self.call("press_read", operation="team.context", params={})["result"])
        self.assertEqual(context["resolved_team"], "team-beta")
        self.assertFalse(context["team_matches_config"])
        self.assertNotIn("partner@example.test", json.dumps(context))
        with self.assertRaises(PreconditionError) as caught:
            self.call("press_propose", operation="release_group.create",
                      params={"title": "x-school", "version": "Version 16", "cluster": "Default",
                              "apps": [{"app": "frappe", "source": "SRC-frappe-1"}]})
        self.assertIn("team.resolved_matches_config", _failed_ids(caught.exception))

    def test_m9_tracker_flags_group_created_under_other_team(self):
        proposal = self.call("press_propose", operation="release_group.create",
                             params={"title": "y-school", "version": "Version 16", "cluster": "Default",
                                     "apps": [{"app": "frappe", "source": "SRC-frappe-1"}]})
        approve(self.ctx, proposal["proposal_id"])
        executed = self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertEqual(executed["state"], "accepted")
        # Yürütme sırasında üyelik kalktı: Press grubu varsayılan takımda yarattı ve okumada da ona düşer.
        self.fake.groups[_untrusted(executed)["references"]["release_group"]]["team"] = "team-beta"
        self.fake.member_teams, self.fake.default_team = {"team-beta"}, "team-beta"
        self.assertEqual(self.call("press_track", proposal_id=proposal["proposal_id"])["state"], "failed")

    def test_m4_ambiguous_site_job_match_is_unknown(self):
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        approve(self.ctx, proposal["proposal_id"])
        self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.fake.add_job("Backup Site", "Success", site="school.example.test")  # zamanlanmış ikinci yedek
        tracked = self.call("press_track", proposal_id=proposal["proposal_id"])
        self.assertEqual(tracked["state"], "unknown")
        self.assertEqual(len(_untrusted(tracked)["evidence"]["candidates"]), 2)

    def test_m8_press_derived_output_is_enveloped(self):
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        self.assertIn("checks", _untrusted(proposal["preview"]))
        approve(self.ctx, proposal["proposal_id"])
        executed = self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertIn("response", _untrusted(executed))
        self.assertNotIn("response", executed)
        self.assertIn("untrusted_data", executed["checks"][0]["evidence"])
        tracked = self.call("press_track", proposal_id=proposal["proposal_id"])
        self.assertIn("evidence", _untrusted(tracked))
        self.assertNotIn("evidence", tracked)


class BackupAge(unittest.TestCase):
    NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=dt.timezone.utc)

    def test_window_holds_in_every_timezone(self):
        verdict = press_ops.backup_age_verdict
        self.assertTrue(verdict("2026-10-08 14:30:00", self.NOW))   # UTC+3 Press, 30 dk önce
        self.assertTrue(verdict("2026-10-08 03:00:00", self.NOW))   # 9 sa saf fark
        self.assertIsNone(verdict("2026-10-07 20:00:00", self.NOW))  # 16 sa: dilime göre değişir
        self.assertFalse(verdict("2026-10-06 20:00:00", self.NOW))  # 40 sa
        self.assertIsNone(verdict("not a date", self.NOW))


if __name__ == "__main__":
    unittest.main()
