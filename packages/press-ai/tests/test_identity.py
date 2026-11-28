"""Local HTTP proof of the G-27/G-28/G-82 service embedding boundary."""

import datetime as dt
import json
import unittest
from unittest.mock import patch

from support import PressCase, approve
from press_ai import credentials
from press_ai.config import PressConfig
from press_ai.errors import ApprovalError, ConfigError, KitError, PressError
from press_ai.tools import Context, Toolbox


class IdentityBoundary(PressCase):
    MUTATIONS = ("site.backup", "deploy_candidate.create")

    def configure(self, identity="delegated", principal="team", **extra):
        data = {"base_url": self.server.url, "principal": principal, "team": self.TEAM,
                "identity": identity, "allow_insecure_loopback": True,
                "enabled_mutations": list(self.MUTATIONS)}
        data.update(extra)
        self.config.press = PressConfig(data)

    def delegated(self, subject=None, audience=None, expires=None, token="press-grant-local"):
        self.configure()
        grant = credentials.DelegatedBearer(
            token, subject or self.fake.user, audience or self.server.url,
            self.clock() + dt.timedelta(seconds=expires if expires is not None else 300),
            clock=self.clock,
        )
        self.fake.delegated_tokens = {"press-grant-local": self.fake.user}
        self.ctx = Context(self.config, clock=self.clock, delegated_bearer=grant)
        self.tools = Toolbox(self.ctx)
        return grant

    def service(self):
        self.fake.principal = "operator"
        self.configure("service_account", "operator", subject=self.fake.user,
                       credentials={"source": "file", "path": self.home.credentials()})
        self.ctx = Context(self.config, clock=self.clock)
        self.tools = Toolbox(self.ctx)

    def test_delegated_grant_runs_as_press_user_and_never_persists_token(self):
        grant = self.delegated()
        result = self.call("press_read", operation="team.context")
        self.assertIn(self.fake.user, json.dumps(result))
        self.assertTrue(all(h["Authorization"] == "Bearer press-grant-local"
                            for _, _, h in self.fake.requests))
        state = self.state_text()
        self.assertIn('"identity":"delegated"', state.replace(" ", ""))
        self.assertIn("tool_completed", state)
        self.assertNotIn("press-grant-local", state + repr(grant) + json.dumps(result))

    def test_expired_grant_is_rejected_without_network(self):
        self.delegated()
        self.clock.advance(seconds=300)
        with self.assertRaises(ConfigError):
            self.call("press_read", operation="team.context")
        self.assertEqual(self.fake.requests, [])

    def test_long_lived_grant_is_refused(self):
        with self.assertRaises(ConfigError):
            self.delegated(expires=301)

    def test_wrong_audience_is_rejected_without_network(self):
        self.delegated(audience="https://other.example.test")
        with self.assertRaises(ConfigError):
            self.call("press_read", operation="team.context")
        self.assertEqual(self.fake.requests, [])

    def test_press_user_mismatch_stops_before_operation(self):
        self.delegated(subject="other@example.test")
        with self.assertRaises(ConfigError):
            self.call("press_read", operation="release_group.list")
        self.assertEqual(self.methods(), ["frappe.auth.get_logged_user"])

    def test_keycloak_or_revoked_bearer_is_not_a_press_grant(self):
        self.delegated(token="keycloak-login-only")
        with self.assertRaises(PressError):
            self.call("press_read", operation="team.context")
        self.assertEqual(len(self.fake.requests), 1)
        self.assertIn("tool_failed", self.state_text())

    def test_revocation_is_checked_again_on_next_tool(self):
        self.delegated()
        self.call("press_read", operation="team.context")
        self.fake.delegated_tokens.clear()
        with self.assertRaises(PressError):
            self.call("press_read", operation="release_group.list")
        self.assertEqual(self.methods()[-1], "frappe.auth.get_logged_user")

    def test_delegated_mode_cannot_read_persistent_credentials(self):
        with self.assertRaises(ConfigError):
            self.configure(credentials={"source": "file", "path": self.home.credentials()})

    def test_delegated_mode_needs_runtime_grant(self):
        self.configure()
        with self.assertRaises(ConfigError):
            Context(self.config, clock=self.clock).press()

    def test_service_mode_requires_operator_and_named_account(self):
        for principal, subject in (("team", self.fake.user), ("operator", None)):
            with self.subTest(principal=principal, subject=subject), self.assertRaises(ConfigError):
                self.configure("service_account", principal, subject=subject,
                               credentials={"source": "file", "path": self.home.credentials()})

    def test_service_cannot_use_customer_or_workspace_tools(self):
        self.service()
        cases = [("press_propose", {"operation": "site.backup", "params": {"site": "school.example.test"}}),
                 ("press_read", {"operation": "site.https_check", "params": {"site": "school.example.test"}}),
                 ("app_inspect", {"app_path": "sample_app"})]
        for tool, args in cases:
            with self.subTest(tool=tool), self.assertRaises(ConfigError):
                self.call(tool, **args)
        self.assertEqual(self.fake.requests, [])

    def test_service_proposal_is_preview_and_cannot_execute_without_approval(self):
        self.service()
        result = self.call("press_propose", operation="deploy_candidate.create",
                           params={"release_group": "bench-0042"})
        self.assertEqual(result["state"], "pending")
        with self.assertRaises(ApprovalError):
            self.call("press_execute", proposal_id=result["proposal_id"])
        self.assertNotIn("run_doc_method", self.methods())

    def test_subject_change_after_approval_blocks_execution(self):
        self.delegated()
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        approve(self.ctx, proposal["proposal_id"])
        self.fake.user = "other@example.test"
        self.delegated()
        with self.assertRaises(ApprovalError) as caught:
            self.call("press_execute", proposal_id=proposal["proposal_id"])
        self.assertEqual(caught.exception.code, "authority_changed")
        self.assertNotIn("press.api.site.backup", self.methods())

    def test_missing_audit_stops_before_network(self):
        self.delegated()
        _ = self.ctx.store
        with patch("press_ai.proposals.os.open", side_effect=PermissionError("read only")):
            with self.assertRaises(ConfigError):
                self.call("press_read", operation="team.context")
        self.assertEqual(self.fake.requests, [])

    def test_service_account_must_match_authenticated_user(self):
        self.service()
        self.fake.user = "other@example.test"
        with self.assertRaises(ConfigError):
            self.call("press_read", operation="press.version")
        self.assertEqual(self.methods(), ["frappe.auth.get_logged_user"])

    def test_invalid_first_tool_name_cannot_leak_delegated_token(self):
        self.delegated()
        with self.assertRaises(KitError):
            self.call("press-grant-local")
        self.assertNotIn("press-grant-local", self.state_text())
        self.assertEqual(self.fake.requests, [])

    def test_call_audit_identifies_read_and_proposal(self):
        self.delegated()
        self.call("press_read", operation="team.context")
        proposal = self.call("press_propose", operation="site.backup", params={"site": "school.example.test"})
        with self.assertRaises(ApprovalError):
            self.call("press_execute", proposal_id=proposal["proposal_id"])
        with open(self.home.path("state", "audit.jsonl")) as handle:
            events = [json.loads(line) for line in handle]
        reads = [event for event in events if event.get("tool") == "press_read"]
        self.assertTrue(reads)
        self.assertTrue(all(event.get("operation") == "team.context" for event in reads))
        self.assertTrue(all(event.get("team") == self.TEAM for event in reads))
        denied = next(event for event in events
                      if event.get("tool") == "press_execute" and event["event"] == "tool_failed")
        self.assertEqual(denied.get("proposal_id"), proposal["proposal_id"])


if __name__ == "__main__":
    unittest.main()
