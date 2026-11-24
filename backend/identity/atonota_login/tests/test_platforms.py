"""Platform registry tests (G-159, O-51).

Expected values come from the product decisions (.pane decisions 6 and 9), G-159 and
docs/dagitim/ortamlar.md. The tests apply one rule to every record, never a fixed platform list.
"""

import json
import re
import secrets
import tempfile
import unittest
from pathlib import Path

from atonota_login import platforms
from atonota_login.platforms import RegistryError

PRODUCT = Path(__file__).resolve().parents[1]
BACKEND = PRODUCT.parents[1]
REALM_FILE = BACKEND / "identity" / "keycloak" / "realm" / "platform-realm.json"
ENVIRONMENTS = BACKEND / "deploy" / "environments"
DEV_ENV_EXAMPLE = BACKEND / "identity" / "keycloak" / ".env.example"
DEV_COMPOSE = BACKEND / "dev" / "compose.keycloak.yaml"
PRODUCTION_ENV_EXAMPLE = BACKEND / "identity" / "keycloak" / "production.env.example"
HANDOFF = BACKEND / "docs" / "handoff" / "atonota-login-platforms.md"


def write_record(directory: Path, record: dict) -> None:
    (directory / f"{record['alias']}.json").write_text(json.dumps(record), encoding="utf-8")


def sample_record(alias: str = "sample-oidc") -> dict:
    upper = alias.upper().replace("-", "_")
    return {
        "alias": alias,
        "providerId": "oidc",
        "displayName": "Sample",
        "authorizationHost": "login.example.test",
        "secrets": {"clientId": f"ATONOTA_{upper}_CLIENT_ID", "clientSecret": f"ATONOTA_{upper}_CLIENT_SECRET"},
        "config": {
            "syncMode": "IMPORT", "authorizationUrl": "https://login.example.test/authorize",
            "filteredByClaim": "true", "claimFilterName": "email_verified", "claimFilterValue": "true",
        },
    }


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = platforms.load_platforms()

    def test_ready_records_exist_for_the_four_named_platforms(self):
        # Decision 6 names Google, Facebook, LinkedIn and X. Apple was already in the realm (O-6).
        aliases = {p.alias for p in self.registry}
        self.assertLessEqual({"google", "facebook", "linkedin", "x", "apple"}, aliases)

    def test_code_holds_no_platform_list(self):
        source = (PRODUCT / "atonota_login" / "platforms.py").read_text(encoding="utf-8").lower()
        for platform in self.registry:
            self.assertNotIn(f'"{platform.alias}"', source, platform.alias)
            self.assertNotIn(f"'{platform.alias}'", source, platform.alias)

    def test_every_record_keeps_secrets_out_of_the_data(self):
        for platform in self.registry:
            self.assertIn("clientId", platform.secrets, platform.alias)
            for name in platform.secrets.values():
                self.assertRegex(name, r"^ATONOTA_[A-Z0-9_]+$", platform.alias)
            for key, value in platform.config.items():
                self.assertNotRegex(key.lower(), "secret|password|private", platform.alias)
                self.assertNotIn("${", str(value), platform.alias)

    def test_secret_names_are_unique(self):
        names = [n for p in self.registry for n in p.secrets.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_a_new_platform_is_only_a_data_file(self):
        with tempfile.TemporaryDirectory() as folder:
            write_record(Path(folder), sample_record())
            loaded = platforms.load_platforms(Path(folder))
        self.assertEqual([p.alias for p in loaded], ["sample-oidc"])
        entry = platforms.realm_entry(loaded[0])
        self.assertEqual(entry["providerId"], "oidc")
        self.assertEqual(entry["config"]["clientId"], "${ATONOTA_SAMPLE_OIDC_CLIENT_ID}")

    def test_invalid_records_are_refused(self):
        bad = [
            ("file name differs", lambda r: r, "other-name"),
            ("trust e-mail", lambda r: {**r, "trustEmail": True}, None),
            ("flow override", lambda r: {**r, "firstBrokerLoginFlowAlias": "first broker login"}, None),
            ("secret in config", lambda r: {**r, "config": {**r["config"], "clientSecret": "x"}}, None),
            ("placeholder in config", lambda r: {**r, "config": {"x": "${ATONOTA_A}"}}, None),
            ("no client id", lambda r: {**r, "secrets": {"clientSecret": "ATONOTA_ONLY_SECRET"}}, None),
            ("bad env name", lambda r: {**r, "secrets": {"clientId": "GOOGLE_ID"}}, None),
            ("bad alias", lambda r: {**r, "alias": "Bad Alias"}, None),
            ("bad host", lambda r: {**r, "authorizationHost": "https://x.test/path"}, None),
            ("unknown key", lambda r: {**r, "enabled": True}, None),
            # Review 1, minor 4: values that turn off a safety check.
            ("signature off", lambda r: {**r, "config": {**r["config"], "validateSignature": "false"}}, None),
            ("no client auth", lambda r: {**r, "config": {**r["config"], "clientAuthMethod": "none"}}, None),
            ("pkce off", lambda r: {**r, "config": {**r["config"], "pkceEnabled": "false"}}, None),
            ("plain endpoint", lambda r: {**r, "config": {**r["config"], "tokenUrl": "http://login.example.test/token"}}, None),
        ]
        for label, change, file_name in bad:
            with self.subTest(label), tempfile.TemporaryDirectory() as folder:
                record = change(sample_record())
                name = file_name or record["alias"]
                (Path(folder) / f"{name}.json").write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaises(RegistryError):
                    platforms.load_platforms(Path(folder))

    def test_open_platform_must_require_a_verified_e_mail(self):
        # Review finding 1 (pre-hijack): a platform that passes an unverified e-mail lets someone claim
        # another person's address before that person registers. An active record must require the
        # provider's email_verified claim. A platform that cannot send it stays inactive.
        for key in ("filteredByClaim", "claimFilterName", "claimFilterValue"):
            with self.subTest(missing=key), tempfile.TemporaryDirectory() as folder:
                record = sample_record()
                del record["config"][key]
                write_record(Path(folder), record)
                with self.assertRaises(RegistryError):
                    platforms.load_platforms(Path(folder))
        with tempfile.TemporaryDirectory() as folder:
            record = sample_record()
            record["config"]["claimFilterValue"] = "false"
            write_record(Path(folder), record)
            with self.assertRaises(RegistryError):
                platforms.load_platforms(Path(folder))
        with tempfile.TemporaryDirectory() as folder:
            record = {**sample_record(), "active": False}
            for key in ("filteredByClaim", "claimFilterName", "claimFilterValue"):
                del record["config"][key]
            write_record(Path(folder), record)
            self.assertFalse(platforms.load_platforms(Path(folder))[0].active)

    def test_switch_named_like_an_address_is_not_an_address(self):
        # Live finding: Keycloak's "useJwksUrl" switch holds "true", not an address.
        with tempfile.TemporaryDirectory() as folder:
            record = sample_record()
            record["config"].update(useJwksUrl="true", issuer="http://identity.localhost:5280/realms/x")
            write_record(Path(folder), record)
            self.assertEqual(len(platforms.load_platforms(Path(folder), allow_local_http=True)), 1)
        with tempfile.TemporaryDirectory() as folder:
            record = sample_record()
            record["config"]["issuer"] = "http://login.example.test/realms/x"
            write_record(Path(folder), record)
            with self.assertRaises(RegistryError):
                platforms.load_platforms(Path(folder))

    def test_local_http_address_is_only_for_development(self):
        # Review 2, finding 2: the registry reaches every environment. In production Keycloak would
        # look for http://localhost on its own machine. Only the development path may allow it.
        for url in ("http://localhost/token", "http://127.0.0.1/token", "http://identity.localhost:5280/token"):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as folder:
                record = sample_record()
                record["config"]["tokenUrl"] = url
                write_record(Path(folder), record)
                with self.assertRaises(RegistryError):
                    platforms.load_platforms(Path(folder))
                self.assertEqual(platforms.load_platforms(Path(folder), allow_local_http=True)[0].config["tokenUrl"], url)
        with tempfile.TemporaryDirectory() as folder:
            record = sample_record()
            record["config"]["tokenUrl"] = "http://login.example.test/token"
            write_record(Path(folder), record)
            with self.assertRaises(RegistryError):
                platforms.load_platforms(Path(folder), allow_local_http=True)

    def test_duplicate_secret_name_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            first = sample_record("one")
            second = sample_record("two")
            second["secrets"] = dict(first["secrets"])
            write_record(Path(folder), first)
            write_record(Path(folder), second)
            with self.assertRaises(RegistryError):
                platforms.load_platforms(Path(folder))


class RealmBindingTest(unittest.TestCase):
    def setUp(self):
        self.realm = json.loads(REALM_FILE.read_text(encoding="utf-8"))
        self.registry = platforms.load_platforms()

    def test_realm_file_is_rendered_from_the_registry(self):
        # A platform enters the realm only through the registry (bin/atonota-login render --write).
        self.assertEqual(self.realm["identityProviders"], platforms.render_identity_providers(self.registry))

    def test_realm_entries_start_closed_and_hidden(self):
        for entry in self.realm["identityProviders"]:
            self.assertFalse(entry["enabled"], entry["alias"])
            self.assertTrue(entry["hideOnLogin"], entry["alias"])
            self.assertFalse(entry["trustEmail"], entry["alias"])
            self.assertEqual(entry["firstBrokerLoginFlowAlias"], platforms.FIRST_BROKER_FLOW, entry["alias"])
            self.assertEqual(entry["postBrokerLoginFlowAlias"], platforms.POST_BROKER_FLOW, entry["alias"])

    def test_render_check_finds_a_changed_realm(self):
        text = REALM_FILE.read_text(encoding="utf-8")
        self.assertEqual(platforms.replace_identity_providers(text, self.registry), text)
        changed = text.replace('"displayName": "Google"', '"displayName": "Changed"', 1)
        self.assertNotEqual(platforms.replace_identity_providers(changed, self.registry), changed)

    def test_every_secret_name_reaches_keycloak_in_development(self):
        example = set(re.findall(r"^([A-Z0-9_]+)=", DEV_ENV_EXAMPLE.read_text(encoding="utf-8"), re.M))
        production = set(re.findall(r"^([A-Z0-9_]+)=", PRODUCTION_ENV_EXAMPLE.read_text(encoding="utf-8"), re.M))
        compose = DEV_COMPOSE.read_text(encoding="utf-8")
        for platform in self.registry:
            for name in platform.secrets.values():
                self.assertIn(name, example, name)
                self.assertIn(name, production, name)
                # An empty value is allowed: the platform then stays closed.
                self.assertIn(f"{name}: ${{{name}:-}}", compose, name)

    def test_development_example_opens_no_platform(self):
        values = dict(re.findall(r"^([A-Z0-9_]+)=(.*)$", DEV_ENV_EXAMPLE.read_text(encoding="utf-8"), re.M))
        for platform in self.registry:
            state = platforms.desired_state(platform, values)
            self.assertFalse(state["enabled"], platform.alias)


class DesiredStateTest(unittest.TestCase):
    def setUp(self):
        self.platform = platforms.load_platforms()[0]

    def environment(self, **overrides):
        values = {name: secrets.token_urlsafe(12) for name in self.platform.secrets.values()}
        values.update(overrides)
        return values

    def test_platform_with_all_secrets_opens_and_shows(self):
        environment = self.environment()
        state = platforms.desired_state(self.platform, environment)
        self.assertTrue(state["enabled"])
        self.assertFalse(state["hideOnLogin"])
        for key, name in self.platform.secrets.items():
            self.assertEqual(state["config"][key], environment[name])

    def test_platform_without_a_secret_stays_closed_and_hidden(self):
        for name in self.platform.secrets.values():
            for missing in ({name: ""}, {name: "   "}):
                with self.subTest(name=name, value=repr(missing[name])):
                    state = platforms.desired_state(self.platform, self.environment(**missing))
                    self.assertFalse(state["enabled"])
                    self.assertTrue(state["hideOnLogin"])
                    for key in self.platform.secrets:
                        self.assertEqual(state["config"].get(key, ""), "")

    def test_inactive_record_stays_closed_with_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            write_record(Path(folder), {**sample_record(), "active": False})
            (platform,) = platforms.load_platforms(Path(folder))
        values = {name: secrets.token_urlsafe(12) for name in platform.secrets.values()}
        self.assertFalse(platforms.desired_state(platform, values)["enabled"])

    def test_state_keeps_the_fixed_safety_fields(self):
        state = platforms.desired_state(self.platform, self.environment())
        self.assertFalse(state["trustEmail"])
        self.assertFalse(state["linkOnly"])
        self.assertEqual(state["firstBrokerLoginFlowAlias"], platforms.FIRST_BROKER_FLOW)


class RedirectTest(unittest.TestCase):
    def test_redirect_uses_the_login_host_and_the_broker_path(self):
        self.assertEqual(
            platforms.broker_redirect_uri("https://api.login.atonota.net", "google"),
            "https://api.login.atonota.net/realms/platform/broker/google/endpoint",
        )

    def test_every_environment_uses_the_login_name_rule(self):
        # docs/dagitim/ortamlar.md: the login host is api.login.<environment base>.
        files = sorted(ENVIRONMENTS.glob("*.env"))
        self.assertEqual({f.stem for f in files}, {"alpha", "beta", "rc", "prod"})
        for path in files:
            values = platforms.read_env_file(path)
            with self.subTest(environment=path.stem):
                self.assertEqual(values["ATONOTA_ID_HOST"], "api.login." + values["ATONOTA_BASE_HOST"])
                table = platforms.environment_redirects(values)
                for platform in platforms.load_platforms():
                    self.assertEqual(
                        table[platform.alias],
                        f"https://api.login.{values['ATONOTA_BASE_HOST']}/realms/platform/broker/{platform.alias}/endpoint",
                    )

    def test_a_host_that_breaks_the_rule_is_refused(self):
        for values in (
            {"ATONOTA_BASE_HOST": "alpha.atonota.net", "ATONOTA_ID_HOST": "id.alpha.atonota.net"},
            {"ATONOTA_BASE_HOST": "alpha.atonota.net", "ATONOTA_ID_HOST": "api.login.atonota.net"},
            {"ATONOTA_BASE_HOST": "alpha.atonota.net", "ATONOTA_ID_HOST": "api.login.alpha.atonota.net/x"},
        ):
            with self.subTest(values=values), self.assertRaises(RegistryError):
                platforms.environment_redirects(values)

    def test_redirect_refuses_unsafe_addresses(self):
        for url in ("http://api.login.atonota.net", "https://user@login.example.test", "https://h.test/path", "ftp://x"):
            with self.subTest(url=url), self.assertRaises(RegistryError):
                platforms.broker_redirect_uri(url, "google")

    def test_local_development_may_use_http(self):
        self.assertEqual(
            platforms.broker_redirect_uri("http://identity.localhost:5280", "google", allow_local_http=True),
            "http://identity.localhost:5280/realms/platform/broker/google/endpoint",
        )

    def test_handoff_lists_every_platform(self):
        text = HANDOFF.read_text(encoding="utf-8")
        for platform in platforms.load_platforms():
            self.assertIn(f"`{platform.alias}`", text, platform.alias)
            self.assertIn(platform.authorization_host, text, platform.alias)


if __name__ == "__main__":
    unittest.main()
