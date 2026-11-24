"""Offline tests of the corporate provider check in the apply step (G-160, AJA-229).

A provider that is not in the platform registry is a corporate provider. It must require the
email_verified claim. Without the claim it needs a valid exception record. Otherwise the command
stops with an error; a warning is not enough (security opinion AJA-212).

The rules come from platform_core/identity/enterprise_rules.py. The command loads that file by path.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from atonota_login import keycloak_apply, platforms
from atonota_login.keycloak_apply import ApplyError

from tests.test_keycloak_apply import FakeKeycloak, record

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
ISSUER = "https://login.microsoftonline.com/0b5e3b55-1f4c-4d2e-9a77-1c2d3e4f5a6b/v2.0"
REALM_FILE = Path(__file__).resolve().parents[3] / "identity" / "keycloak" / "realm" / "platform-realm.json"


def grant(alias="acme-entra", **changes):
    value = {
        "name": "EIDP-0001",
        "kind": "grant",
        "provider_alias": alias,
        "issuer": ISSUER,
        "organization": "acme",
        "allowed_domains": [
            {
                "domain": "acme.example",
                "verification_method": "dns-txt",
                "verified_on": "2026-11-20T09:00:00+00:00",
                "verification_record": "_atonota-verify.acme.example",
            }
        ],
        "reason": "The provider does not send the email_verified claim.",
        "provider_document": "https://docs.example/provider/claims",
        "requested_by": "owner@acme.example",
        "approved_by": "security@platform.example",
        "approval_principal": "human_session",
        "approved_on": "2026-11-21T10:00:00+00:00",
        "expires_on": "2027-01-01T00:00:00+00:00",
        "supersedes": None,
    }
    value.update(changes)
    return value


def corporate(alias="acme-entra", provider_id="oidc", rule=False, **changes):
    config = {"clientId": "c", "issuer": ISSUER}
    if rule:
        config.update(platforms.VERIFIED_EMAIL_CLAIM)
    value = {
        "alias": alias,
        "providerId": provider_id,
        "enabled": True,
        "trustEmail": False,
        "firstBrokerLoginFlowAlias": platforms.FIRST_BROKER_FLOW,
        "postBrokerLoginFlowAlias": platforms.POST_BROKER_FLOW,
        "config": config,
    }
    value.update(changes)
    return value


class EnterpriseApplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = keycloak_apply.load_enterprise_rules()

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for alias in ("open-one", "closed-one"):
            (Path(folder.name) / f"{alias}.json").write_text(json.dumps(record(alias)), encoding="utf-8")
        self.registry = platforms.load_platforms(Path(folder.name))
        self.environment = {"ATONOTA_OPEN_ONE_CLIENT_ID": "client-1", "ATONOTA_OPEN_ONE_CLIENT_SECRET": "s3"}

    def run_apply(self, providers, exceptions=(), now=NOW, rules="default"):
        keycloak = FakeKeycloak(providers)
        report = keycloak_apply.apply_registry(
            keycloak,
            self.registry,
            self.environment,
            exceptions=list(exceptions),
            rules=self.rules if rules == "default" else rules,
            now=now,
        )
        return keycloak, report

    def assertRefused(self, rule, providers, exceptions=(), **keywords):
        with self.assertRaises(ApplyError) as raised:
            self.run_apply(providers, exceptions, **keywords)
        self.assertEqual(raised.exception.rule, rule)
        return raised.exception

    # Accepted paths.

    def test_provider_with_the_rule_passes_without_exception(self):
        _, report = self.run_apply([corporate(rule=True)])
        self.assertIn({"alias": "acme-entra", "action": "not-in-registry", "enabled": True}, report)

    def test_provider_with_valid_exception_passes(self):
        keycloak, report = self.run_apply([corporate()], [grant()])
        self.assertIn(
            {"alias": "acme-entra", "action": "not-in-registry-exception", "enabled": True, "exception": "EIDP-0001"},
            report,
        )
        self.assertFalse([w for w in keycloak.writes if "acme-entra" in w[1]])

    # Rejected cases of the task (2, 7 and 10) and the extra checks of the design.

    def test_unregistered_provider_without_exception_fails(self):
        error = self.assertRefused("missing_exception", [corporate()])
        self.assertIn("acme-entra", str(error))

    def test_social_platform_cannot_use_exception(self):
        # Case 2: a social provider type, or a social platform name, never takes an exception.
        self.assertRefused("social_platform", [corporate("google-corp", "google")], [grant("google-corp")])
        self.assertRefused("social_platform", [corporate("facebook")], [grant("facebook")])

    def test_trust_email_on_is_rejected(self):
        # Case 7: checked before the exception and before the rule.
        for provider in (
            corporate(trustEmail=True),
            corporate(rule=True, trustEmail=True),
            corporate(rule=True, config={**corporate(rule=True)["config"], "trustEmail": "true"}),
        ):
            with self.subTest(provider=provider):
                self.assertRefused("trust_email", [provider], [grant()])

    def test_expired_exception_is_rejected(self):
        # Case 10: a fixed clock, never the real one.
        later = datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc)
        self.assertRefused("expired", [corporate()], [grant()], now=later)

    def test_record_rule_break_stops_the_command(self):
        record_with_public_domain = grant()
        record_with_public_domain["allowed_domains"][0]["domain"] = "gmail.com"
        self.assertRefused("public_mail_domain", [corporate()], [record_with_public_domain])
        self.assertRefused("self_approval", [corporate()], [grant(approved_by="owner@acme.example")])
        self.assertRefused("expiry_missing", [corporate()], [grant(expires_on=None)])

    def test_issuer_must_match_the_provider(self):
        provider = corporate(config={"clientId": "c", "issuer": ISSUER.replace("0b5e", "ffff")})
        self.assertRefused("issuer_mismatch", [provider], [grant()])

    def test_broker_flows_must_stay_fixed(self):
        for key in ("firstBrokerLoginFlowAlias", "postBrokerLoginFlowAlias"):
            with self.subTest(key=key):
                self.assertRefused("broker_flow", [corporate(rule=True, **{key: "first broker login"})])
                self.assertRefused("broker_flow", [corporate(**{key: None})], [grant()])

    def test_revocation_is_not_an_exception(self):
        revocation = {"name": "EIDP-0002", "kind": "revocation", "provider_alias": "acme-entra",
                      "organization": "acme", "reason": "Closed.", "requested_by": "owner@acme.example",
                      "supersedes": "EIDP-0001"}
        self.assertRefused("revoked", [corporate()], [revocation])

    def test_exception_needs_the_rules_module(self):
        self.assertRefused("rules_missing", [corporate()], [grant()], rules=None)

    def test_error_names_only_the_provider_and_the_rule(self):
        leaked = grant()
        # A fake key header. It matches the record check but is not a real key format.
        leaked["reason"] = "-----BEGIN TEST KEY----- abc"
        error = self.assertRefused("secret_in_record", [corporate()], [leaked])
        self.assertNotIn("BEGIN", str(error))
        self.assertEqual(str(error), "Corporate provider acme-entra refused: secret_in_record.")

    def test_desired_state_keeps_trust_email_off(self):
        # trustEmail stays off in every case: the registry writes false, even when a record asks for
        # true, and the command never writes a corporate provider.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        asking = record("open-one")
        asking["config"]["trustEmail"] = "true"
        (Path(folder.name) / "open-one.json").write_text(json.dumps(asking), encoding="utf-8")
        self.registry = platforms.load_platforms(Path(folder.name))
        old = {"alias": "open-one", "providerId": "oidc", "enabled": True, "trustEmail": True, "config": {}}
        keycloak, _ = self.run_apply([old, corporate()], [grant()])
        self.assertTrue(keycloak.writes)
        for _, path, body in keycloak.writes:
            self.assertIs(json.loads(body)["trustEmail"], False)
            self.assertNotIn("acme-entra", path)
        self.assertIs(keycloak.providers["open-one"]["trustEmail"], False)
        self.assertIs(keycloak.providers["acme-entra"]["trustEmail"], False)

    def test_exception_keeps_enterprise_sso_flow(self):
        # The exception does not touch the enterprise-sso-required rule. The command writes no flow
        # and the realm file keeps the role condition.
        before = REALM_FILE.read_bytes()
        keycloak, _ = self.run_apply([corporate()], [grant()])
        self.assertEqual(REALM_FILE.read_bytes(), before)
        for _, path, body in keycloak.writes:
            self.assertTrue(path.startswith("/identity-provider/instances"))
            self.assertNotIn("enterprise-sso-required", body)
        realm = json.loads(before)
        conditions = [c["config"].get("condUserRole") for c in realm["authenticatorConfig"]]
        self.assertIn("enterprise-sso-required", conditions)


class SocialListTest(unittest.TestCase):
    def test_rules_name_every_product_platform(self):
        # The rules module runs without this folder inside the application server, so it keeps its own
        # copy of the social aliases. This test keeps the copy equal to the platform records.
        rules = keycloak_apply.load_enterprise_rules()
        stems = {path.stem for path in platforms.REGISTRY_DIR.glob("*.json")}
        self.assertEqual(set(rules.SOCIAL_PROVIDER_ALIASES), stems)
        provider_ids = {p.provider_id for p in platforms.load_platforms(platforms.REGISTRY_DIR)}
        self.assertLessEqual(provider_ids, set(rules.SOCIAL_PROVIDER_IDS))


class ExceptionFileTest(unittest.TestCase):
    def write(self, value):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "exceptions.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_file_holds_a_list(self):
        self.assertEqual(keycloak_apply.read_exceptions(self.write([grant()])), [grant()])
        for value in ({"a": 1}, [1], "x"):
            with self.subTest(value=value), self.assertRaises(ApplyError):
                keycloak_apply.read_exceptions(self.write(value))

    def test_one_record_per_provider(self):
        # One exception is for one provider and one organisation. A provider alias is realm wide.
        with self.assertRaises(ApplyError) as raised:
            keycloak_apply.read_exceptions(self.write([grant(), grant(organization="other")]))
        self.assertEqual(raised.exception.rule, "duplicate_provider")

    def test_rules_file_must_exist(self):
        with self.assertRaises(ApplyError) as raised:
            keycloak_apply.load_enterprise_rules(Path("/nonexistent/enterprise_rules.py"))
        self.assertEqual(raised.exception.rule, "rules_missing")


class EnterpriseCommandTest(unittest.TestCase):
    """The command line stops on a corporate provider without the rule or an exception."""

    @classmethod
    def setUpClass(cls):
        import importlib.machinery
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "bin" / "atonota-login"
        loader = importlib.machinery.SourceFileLoader("atonota_login_command_enterprise", str(path))
        spec = importlib.util.spec_from_loader("atonota_login_command_enterprise", loader)
        cls.command = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.command)

    def run_command(self, providers, *arguments):
        import contextlib
        import io

        local = {"KC_PUBLIC_URL": "http://identity.localhost:5280", "KC_BOOTSTRAP_ADMIN_USERNAME": "admin",
                 "KC_BOOTSTRAP_ADMIN_PASSWORD": "not-used"}
        loopback = [(2, 1, 6, "", ("127.0.0.1", 0))]
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", local), mock.patch("socket.getaddrinfo", return_value=loopback), \
                mock.patch.object(keycloak_apply, "admin_caller", return_value=FakeKeycloak(providers)), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = self.command.main(["apply", "--from-env", *arguments])
        return code, output.getvalue(), errors.getvalue()

    def exceptions_file(self, value):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "exceptions.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def test_provider_without_rule_and_exception_fails(self):
        code, _, errors = self.run_command([corporate()])
        self.assertEqual(code, 1)
        self.assertIn("acme-entra", errors)
        self.assertIn("missing_exception", errors)

    def test_exception_file_lets_the_provider_pass(self):
        # The test record expires on 1 January 2027. The command uses the real clock, so the test
        # moves the record's dates far ahead to stay valid.
        record_value = grant(expires_on="2999-01-01T00:00:00+00:00")
        code, output, _ = self.run_command(
            [corporate()], "--enterprise-exceptions", self.exceptions_file([record_value])
        )
        self.assertEqual(code, 0)
        self.assertIn("acme-entra: not-in-registry-exception EIDP-0001, open", output)

    def test_missing_rules_file_stops_the_command(self):
        with mock.patch.object(keycloak_apply, "RULES_PATH", Path("/nonexistent/enterprise_rules.py")):
            code, _, errors = self.run_command([corporate(rule=True)])
        self.assertEqual(code, 1)
        self.assertIn("rules_missing", errors)


if __name__ == "__main__":
    unittest.main()
