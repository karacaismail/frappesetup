"""Check the local review accounts command of the shared stack (`stack review-accounts`)."""

import json
import runpy
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import Mock, patch


E2E = Path(__file__).resolve().parents[1]
STACK = E2E / "stack"
ACCOUNTS = E2E / "review-accounts.json"
KEYCLOAK_SCRIPT = E2E / "preview" / "stack-review-keycloak.py"
REALM = E2E.parent / "identity/keycloak/realm/platform-realm.json"
# A fresh value per run, so no credential literal sits in the source.
ADMIN_VALUE = uuid4().hex

LOCAL = {
    "KC_PUBLIC_URL": "http://identity.localhost:6700",
    "ATONOTA_SITE_TENANT1_URL": "http://tenant1.localhost:6701",
    "ATONOTA_PRESS_URL": "http://press.localhost:6703",
    "KC_BOOTSTRAP_ADMIN_USERNAME": "synthetic-admin",
    "KC_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_VALUE,
}


def stack():
    return runpy.run_path(str(STACK))


def completed(payload):
    return Mock(stdout="Frappe noise\n" + json.dumps(payload) + "\n")


class ReviewAccountListTest(unittest.TestCase):
    def test_the_file_names_the_four_review_accounts_with_one_shared_password(self):
        data = json.loads(ACCOUNTS.read_text())
        self.assertIn("local review", data["note"].lower())
        self.assertIsInstance(data["password"], str)
        accounts = {account["username"]: account for account in data["accounts"]}
        self.assertEqual(set(accounts), {
            "inceleme-panel@example.test",
            "inceleme-yonetici@example.test",
            "inceleme-yerel-yonetici",
            "inceleme-press@example.test",
        })
        self.assertEqual(accounts["inceleme-panel@example.test"]["realm"], "platform")
        self.assertEqual(set(accounts["inceleme-panel@example.test"]["tenant_roles"]), {"Employee", "HR User"})
        self.assertTrue(accounts["inceleme-panel@example.test"]["employee"])
        self.assertEqual(accounts["inceleme-yonetici@example.test"]["realm"], "platform")
        self.assertEqual(accounts["inceleme-yonetici@example.test"]["tenant_roles"], ["System Manager"])
        self.assertEqual(accounts["inceleme-yerel-yonetici"]["realm"], "master")
        self.assertEqual(accounts["inceleme-yerel-yonetici"]["master_roles"], ["admin"])
        self.assertEqual(accounts["inceleme-press@example.test"]["realm"], "platform")
        self.assertTrue(accounts["inceleme-press@example.test"]["press"])

    def test_the_loader_returns_the_file_and_rejects_a_changed_list(self):
        load = stack()["load_review_accounts"]
        data = load(ACCOUNTS)
        self.assertEqual(data["password"], json.loads(ACCOUNTS.read_text())["password"])
        broken = json.loads(ACCOUNTS.read_text())
        broken["accounts"][0]["username"] = "someone@example.test"
        with patch.object(Path, "read_text", return_value=json.dumps(broken)):
            with self.assertRaisesRegex(ValueError, "example.test"):
                load(ACCOUNTS)

    def test_the_password_lives_only_in_the_accounts_file(self):
        password = json.loads(ACCOUNTS.read_text())["password"]
        for path in (STACK, *sorted((E2E / "preview").glob("stack-review-*.py"))):
            with self.subTest(path=path.name):
                self.assertNotIn(password, path.read_text())

    def test_the_readme_opens_with_the_panel_sign_in_and_points_to_the_accounts_file(self):
        password = json.loads(ACCOUNTS.read_text())["password"]
        readme = (E2E / "README.md").read_text()
        first = readme.splitlines()[0]
        self.assertIn("http://localhost:5180", first)
        self.assertIn("inceleme-panel@example.test", first)
        self.assertIn("backend/e2e/review-accounts.json", first)
        self.assertNotIn(password, readme)

    def test_the_accounts_file_is_the_only_file_with_the_password(self):
        password = json.loads(ACCOUNTS.read_text())["password"]
        found = [
            path.relative_to(E2E.parent.parent)
            for path in E2E.parent.rglob("*")
            if path.is_file() and path != ACCOUNTS and "node_modules" not in path.parts
            and path.suffix in {".md", ".py", ".json", ".sh", ".yml", ".yaml", ".toml", ".txt", ""}
            and password in path.read_text(errors="ignore")
        ]
        self.assertEqual(found, [])


class LocalStackTest(unittest.TestCase):
    def test_local_addresses_are_accepted(self):
        stack()["require_local_stack"](LOCAL)
        stack()["require_local_stack"]({**LOCAL, "KC_PUBLIC_URL": "http://localhost:6700"})

    def test_other_addresses_are_refused(self):
        require = stack()["require_local_stack"]
        for value in (
            "https://identity.example.com",
            "http://identity.example.com:6700",
            "http://localhost.example.com:6700",
            "http://10.0.0.5:6700",
            "http://identity.localhost:6700/realms",
            "https://identity.localhost:6700",
            "",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "local"):
                    require({**LOCAL, "KC_PUBLIC_URL": value})
        with self.assertRaisesRegex(ValueError, "local"):
            require({**LOCAL, "ATONOTA_PRESS_URL": "https://press.example.com"})

    def test_a_remote_stack_stops_before_any_docker_call(self):
        scope = stack()
        command = scope["review_accounts"]
        with patch.dict(command.__globals__, {"run": Mock()}) as globals_:
            with self.assertRaisesRegex(ValueError, "local"):
                command(["compose"], {**LOCAL, "KC_PUBLIC_URL": "https://identity.example.com"})
            globals_["run"].assert_not_called()

    def test_review_accounts_is_a_stack_action(self):
        self.assertIn("review-accounts", STACK.read_text())

    def test_help_describes_every_action_including_both_merged_commands(self):
        scope = stack()
        self.assertIn("review-accounts", scope["ACTIONS"])
        self.assertIn("seed-preview", scope["ACTIONS"])
        described = [line.split()[0] for line in scope["ACTION_HELP"].splitlines()[1:] if line.strip()]
        self.assertEqual(described, list(scope["ACTIONS"]))


class ReviewAccountsFlowTest(unittest.TestCase):
    def test_accounts_reach_keycloak_tenant_and_press_through_stdin(self):
        command = stack()["review_accounts"]
        password = json.loads(ACCOUNTS.read_text())["password"]
        replies = [
            completed({"subjects": {
                "inceleme-panel@example.test": "sub-panel",
                "inceleme-yonetici@example.test": "sub-admin",
                "inceleme-press@example.test": "sub-press",
            }}),
            completed({"users": ["inceleme-panel@example.test", "inceleme-yonetici@example.test"]}),
            completed({"users": ["inceleme-press@example.test"]}),
        ]
        run = Mock(side_effect=replies)
        with patch.dict(command.__globals__, {"run": run}):
            summary = command(["compose"], dict(LOCAL))
        self.assertEqual(run.call_count, 3)
        for call in run.call_args_list:
            self.assertNotIn(password, " ".join(call.args[0]))
            self.assertNotIn(LOCAL["KC_BOOTSTRAP_ADMIN_PASSWORD"], " ".join(call.args[0]))
        keycloak = json.loads(run.call_args_list[0].kwargs["input"])
        self.assertEqual(keycloak["keycloak_url"], LOCAL["KC_PUBLIC_URL"])
        self.assertEqual(keycloak["password"], password)
        self.assertEqual(keycloak["relaxed_length"], 8)
        self.assertEqual(keycloak["restore_policy"], json.loads(REALM.read_text())["passwordPolicy"])
        tenant = json.loads(run.call_args_list[1].kwargs["input"])
        self.assertEqual(tenant["issuer"], LOCAL["KC_PUBLIC_URL"] + "/realms/platform")
        self.assertEqual(
            {account["email"]: account["subject"] for account in tenant["accounts"]},
            {"inceleme-panel@example.test": "sub-panel", "inceleme-yonetici@example.test": "sub-admin"},
        )
        self.assertNotIn("password", json.dumps(tenant))
        press = json.loads(run.call_args_list[2].kwargs["input"])
        self.assertEqual(press["accounts"], [{"email": "inceleme-press@example.test", "subject": "sub-press"}])
        self.assertNotIn(password, json.dumps(summary))


class FakeKeycloak:
    """Records admin calls of the review script. Platform and master start without the accounts."""

    def __init__(self, policy):
        self.policies = {"platform": policy, "master": None}
        self.users = {"platform": {}, "master": {}}
        self.passwords = []
        self.calls = []

    def __call__(self, method, path, data=None):
        self.calls.append((method, path))
        realm = path.split("/")[3]
        rest = "/" + "/".join(path.split("/")[4:])
        if rest == "/" and method == "GET":
            return 200, None, {"passwordPolicy": self.policies[realm]}
        if rest == "/" and method == "PUT":
            self.policies[realm] = data["passwordPolicy"]
            return 204, None, None
        if rest.startswith("/users?"):
            name = rest.split("username=")[1].split("&")[0].replace("%40", "@")
            user = self.users[realm].get(name)
            return 200, None, [user] if user else []
        if rest == "/users" and method == "POST":
            self.users[realm][data["username"]] = {"id": "id-" + data["username"], **data}
            self.passwords.append((realm, self.policies[realm]))
            return 201, f"http://x/users/id-{data['username']}", None
        if rest.endswith("/reset-password"):
            self.passwords.append((realm, self.policies[realm]))
            return 204, None, None
        if rest.startswith("/users/") and method == "PUT":
            return 204, None, None
        if rest == "/roles/admin":
            return 200, None, {"id": "role-admin", "name": "admin"}
        if rest.endswith("/role-mappings/realm"):
            return 204, None, None
        raise AssertionError(f"Unexpected call {method} {path}")


class KeycloakScriptTest(unittest.TestCase):
    def setUp(self):
        self.script = runpy.run_path(str(KEYCLOAK_SCRIPT))
        self.data = json.loads(ACCOUNTS.read_text())

    def payload(self, url="http://identity.localhost:6700"):
        return {
            "keycloak_url": url,
            "admin_username": "synthetic-admin",
            "admin_password": ADMIN_VALUE,
            "password": self.data["password"],
            "relaxed_length": 8,
            "restore_policy": json.loads(REALM.read_text())["passwordPolicy"],
            "accounts": self.data["accounts"],
        }

    def test_the_production_realm_file_keeps_its_twelve_character_rule(self):
        policy = json.loads(REALM.read_text())["passwordPolicy"]
        self.assertIn("length(12)", policy)
        self.assertNotIn("length(8)", policy)

    def test_relaxed_policy_lowers_only_length_and_the_repeat_blocking_history(self):
        relax = self.script["relaxed_policy"]
        policy = json.loads(REALM.read_text())["passwordPolicy"]
        relaxed = relax(policy, 8)
        self.assertIn("length(8)", relaxed)
        self.assertNotIn("length(12)", relaxed)
        self.assertNotIn("passwordHistory", relaxed)
        for rule in ("passwordBlacklist(common-passwords.txt)", "notUsername", "notEmail"):
            self.assertIn(rule, relaxed)

    def test_the_script_refuses_a_remote_keycloak_before_signing_in(self):
        apply = self.script["apply"]
        for url in ("https://identity.example.com", "http://identity.example.com:6700", "http://10.0.0.5:80"):
            with self.subTest(url=url):
                caller = Mock()
                with self.assertRaises(SystemExit):
                    apply(self.payload(url), caller_factory=caller)
                caller.assert_not_called()

    def test_passwords_are_set_under_the_relaxed_rule_and_the_rule_is_restored(self):
        policy = json.loads(REALM.read_text())["passwordPolicy"]
        keycloak = FakeKeycloak(policy)
        result = self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        self.assertEqual(keycloak.policies["platform"], policy)
        platform_sets = [rule for realm, rule in keycloak.passwords if realm == "platform"]
        self.assertEqual(len(platform_sets), 3)
        self.assertTrue(all("length(8)" in rule for rule in platform_sets))
        self.assertEqual(set(result["subjects"]), {
            "inceleme-panel@example.test", "inceleme-yonetici@example.test", "inceleme-press@example.test",
        })
        self.assertIn(("POST", "/admin/realms/master/users/id-inceleme-yerel-yonetici/role-mappings/realm"),
                      keycloak.calls)
        self.assertNotIn(self.data["password"], json.dumps(result))

    def test_a_rule_left_relaxed_by_a_killed_run_is_replaced_by_the_realm_file_rule(self):
        # A killed earlier run left the relaxed rule in the running Keycloak.
        policy = json.loads(REALM.read_text())["passwordPolicy"]
        keycloak = FakeKeycloak(self.script["relaxed_policy"](policy, 8))
        self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        self.assertEqual(keycloak.policies["platform"], policy)

    def test_a_restore_rule_without_the_production_length_is_refused_before_signing_in(self):
        apply = self.script["apply"]
        policy = json.loads(REALM.read_text())["passwordPolicy"]
        for restore in ("", "length(8) and notUsername", self.script["relaxed_policy"](policy, 8), None):
            with self.subTest(restore=restore):
                caller = Mock()
                with self.assertRaises(SystemExit):
                    apply({**self.payload(), "restore_policy": restore}, caller_factory=caller)
                caller.assert_not_called()

    def test_the_rule_is_restored_when_a_password_update_fails(self):
        policy = json.loads(REALM.read_text())["passwordPolicy"]
        keycloak = FakeKeycloak(policy)
        original = keycloak.__call__

        def failing(method, path, data=None):
            if path.endswith("/users") and method == "POST" and "/platform/" in path:
                return 400, None, {"error": "invalidPassword"}
            return original(method, path, data)

        with self.assertRaises(SystemExit):
            self.script["apply"](self.payload(), caller_factory=lambda *_: failing)
        self.assertEqual(keycloak.policies["platform"], policy)


if __name__ == "__main__":
    unittest.main()
