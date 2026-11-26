"""Check the local review accounts command of the shared stack (`stack review-accounts`)."""

import json
import re
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
COMPOSE = E2E.parent / "dev/compose.identity-sync.yaml"
COMPOSE_ORGANIZATION = re.search(r'"organization":"([a-z0-9-]+)"', COMPOSE.read_text()).group(1)
# A fresh value per run, so no credential literal sits in the source.
ADMIN_VALUE = uuid4().hex

LOCAL = {
    "KC_PUBLIC_URL": "http://identity.localhost:6700",
    "ATONOTA_SITE_TENANT1_URL": "http://tenant1.localhost:6701",
    "ATONOTA_PRESS_URL": "http://press.localhost:6703",
    "KC_BOOTSTRAP_ADMIN_USERNAME": "synthetic-admin",
    "KC_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_VALUE,
}


PANEL_ROLES = {
    "inceleme-yonetici@example.test": "Tenant Admin",
    "inceleme-yonetici-yardimci@example.test": "Tenant Admin Assistant",
    "inceleme-bayi@example.test": "Reseller Admin",
    "inceleme-bayi-yardimci@example.test": "Reseller Assistant",
}
TENANT_ACCOUNTS = ["inceleme-panel@example.test", *PANEL_ROLES]


def stack():
    return runpy.run_path(str(STACK))


def completed(payload):
    return Mock(stdout="Frappe noise\n" + json.dumps(payload) + "\n")


class ReviewAccountListTest(unittest.TestCase):
    def test_the_file_names_the_review_accounts_with_one_shared_password(self):
        data = json.loads(ACCOUNTS.read_text())
        self.assertIn("local review", data["note"].lower())
        self.assertIsInstance(data["password"], str)
        accounts = {account["username"]: account for account in data["accounts"]}
        self.assertEqual(set(accounts), {
            "inceleme-panel@example.test",
            "inceleme-yonetici@example.test",
            "inceleme-yonetici-yardimci@example.test",
            "inceleme-bayi@example.test",
            "inceleme-bayi-yardimci@example.test",
            "inceleme-yerel-yonetici",
            "inceleme-press@example.test",
        })
        self.assertEqual(accounts["inceleme-panel@example.test"]["realm"], "platform")
        self.assertEqual(set(accounts["inceleme-panel@example.test"]["tenant_roles"]), {"Employee", "HR User"})
        self.assertTrue(accounts["inceleme-panel@example.test"]["employee"])
        self.assertEqual(accounts["inceleme-yonetici@example.test"]["realm"], "platform")
        self.assertEqual(accounts["inceleme-yonetici@example.test"]["tenant_roles"], ["Tenant Admin"])
        self.assertEqual(accounts["inceleme-yonetici@example.test"]["user_type"], "Website User")
        # G-53: only the panel administrator account changes. The others keep their shape.
        self.assertNotIn("user_type", accounts["inceleme-panel@example.test"])
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

    def test_the_four_panel_roles_have_one_website_user_account_each_with_its_role_profile(self):
        # G-62, G-168, G-169, G-170: one review account per panel role.
        accounts = json.loads(ACCOUNTS.read_text())["accounts"]
        panel = {account["role_profile"]: account for account in accounts if account.get("role_profile")}
        self.assertEqual(set(panel), set(PANEL_ROLES.values()))
        for username, role in PANEL_ROLES.items():
            with self.subTest(username=username):
                account = panel[role]
                self.assertEqual(account["username"], username)
                self.assertEqual(account["realm"], "platform")
                self.assertEqual(account["user_type"], "Website User")
                self.assertEqual(account["tenant_roles"], [role])

    def test_no_review_account_holds_system_manager(self):
        for account in json.loads(ACCOUNTS.read_text())["accounts"]:
            with self.subTest(username=account["username"]):
                self.assertNotIn("System Manager", account.get("tenant_roles", []))
                self.assertNotEqual(account.get("role_profile"), "System Manager")

    def test_the_loader_refuses_system_manager_on_any_account(self):
        load = stack()["load_review_accounts"]
        for field, value in (("tenant_roles", ["Tenant Admin", "System Manager"]), ("role_profile", "System Manager")):
            with self.subTest(field=field):
                broken = json.loads(ACCOUNTS.read_text())
                broken["accounts"][1][field] = value
                with patch.object(Path, "read_text", return_value=json.dumps(broken)):
                    with self.assertRaisesRegex(ValueError, "System Manager"):
                        load(ACCOUNTS)

    def test_two_resellers_each_have_only_their_own_sample_customer(self):
        links = json.loads(ACCOUNTS.read_text())["reseller_links"]
        resellers = {link["reseller_tenant"] for link in links}
        self.assertEqual(len(resellers), 2)
        # The reseller review accounts sign in on the stack's tenant site.
        self.assertIn("tenant1.localhost", resellers)
        customers = [link["customer_tenant"] for link in links]
        self.assertEqual(len(customers), len(set(customers)))
        for reseller in resellers:
            with self.subTest(reseller=reseller):
                self.assertEqual(len([link for link in links if link["reseller_tenant"] == reseller]), 1)
        for link in links:
            with self.subTest(customer=link["customer_tenant"]):
                self.assertRegex(link["customer_tenant"], r"^[a-z0-9-]+\.example\.test$")
                self.assertTrue(link["customer_name"].startswith("Örnek"))
                self.assertIn(link["site_status"], {"Pending", "Active", "Suspended"})
                self.assertNotIn(link["customer_tenant"], resellers)

    def test_the_loader_refuses_a_customer_outside_example_test_or_linked_twice(self):
        load = stack()["load_review_accounts"]
        cases = {
            "real address": lambda links: links[0].update(customer_tenant="musteri.example.com"),
            "linked twice": lambda links: links[1].update(customer_tenant=links[0]["customer_tenant"]),
            "no name": lambda links: links[0].update(customer_name=""),
            "unknown status": lambda links: links[0].update(site_status="Deleted"),
            "real reseller": lambda links: links[1].update(reseller_tenant="bayi.example.com"),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                broken = json.loads(ACCOUNTS.read_text())
                change(broken["reseller_links"])
                with patch.object(Path, "read_text", return_value=json.dumps(broken)):
                    with self.assertRaisesRegex(ValueError, "reseller"):
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

    def test_the_readme_describes_the_tenant_administrator_with_the_tenant_admin_role(self):
        row = next(line for line in (E2E / "README.md").read_text().splitlines()
                   if line.startswith("| `inceleme-yonetici@example.test`"))
        self.assertIn("“Tenant Admin”", row)
        self.assertIn("“Website User”", row)
        self.assertNotIn("System Manager", row)

    def test_the_readme_describes_each_panel_role_account(self):
        lines = (E2E / "README.md").read_text().splitlines()
        for username, role in PANEL_ROLES.items():
            with self.subTest(username=username):
                row = next(line for line in lines if line.startswith(f"| `{username}`"))
                self.assertIn(f"“{role}”", row)
                self.assertIn("“Website User”", row)
                self.assertNotIn("System Manager", row)

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
                **{email: "sub-" + email for email in TENANT_ACCOUNTS},
                "inceleme-press@example.test": "sub-press",
            }}),
            completed({"users": TENANT_ACCOUNTS}),
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
        # identity-sync of the stack binds tenant1 to this organization (dev/compose.identity-sync.yaml).
        self.assertEqual(keycloak["organization"], COMPOSE_ORGANIZATION)
        tenant = json.loads(run.call_args_list[1].kwargs["input"])
        self.assertEqual(tenant["issuer"], LOCAL["KC_PUBLIC_URL"] + "/realms/platform")
        self.assertEqual(
            {account["email"]: account["subject"] for account in tenant["accounts"]},
            {email: "sub-" + email for email in TENANT_ACCOUNTS},
        )
        self.assertNotIn("password", json.dumps(tenant))
        types = {account["email"]: account.get("user_type") for account in tenant["accounts"]}
        self.assertEqual(types, {"inceleme-panel@example.test": None,
                                 **{email: "Website User" for email in PANEL_ROLES}})
        profiles = {account["email"]: account.get("role_profile") for account in tenant["accounts"]}
        self.assertEqual(profiles, {"inceleme-panel@example.test": None, **PANEL_ROLES})
        self.assertEqual(tenant["reseller_links"], json.loads(ACCOUNTS.read_text())["reseller_links"])
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
        # The stack's tenant organization. A test may remove it or seed earlier members.
        self.organizations = {"org-tenant1": {"id": "org-tenant1", "alias": "tenant1", "name": "Yerel kiracı"},
                              "org-other": {"id": "org-other", "alias": "other", "name": "Other"}}
        self.members = {"org-tenant1": set(), "org-other": set()}

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
        if realm == "platform" and rest.startswith("/organizations?") and method == "GET":
            return 200, None, list(self.organizations.values())
        if realm == "platform" and rest == "/organizations" and method == "POST":
            identifier = "org-" + data["alias"]
            self.organizations[identifier] = {"id": identifier, **data}
            self.members[identifier] = set()
            return 201, f"http://x/organizations/{identifier}", None
        if realm == "platform" and rest.startswith("/organizations/") and rest.endswith("/members") and method == "POST":
            identifier = rest.split("/")[2]
            if data in self.members[identifier]:
                return 409, None, {"errorMessage": "User is already a member of the organization."}
            self.members[identifier].add(data)
            return 201, None, None
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
            "organization": "tenant1",
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
        self.assertEqual(len(platform_sets), 6)
        self.assertTrue(all("length(8)" in rule for rule in platform_sets))
        self.assertEqual(set(result["subjects"]), {*TENANT_ACCOUNTS, "inceleme-press@example.test"})
        self.assertIn(("POST", "/admin/realms/master/users/id-inceleme-yerel-yonetici/role-mappings/realm"),
                      keycloak.calls)
        self.assertNotIn(self.data["password"], json.dumps(result))

    def test_every_tenant_account_becomes_a_member_of_the_tenant_organization(self):
        # AJA-950, G-160: identity-sync answers the linked accounts read only for a member of the
        # tenant's organization. Without the membership the panel shows 403 LoginReadForbidden.
        keycloak = FakeKeycloak(json.loads(REALM.read_text())["passwordPolicy"])
        self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        self.assertEqual(keycloak.members["org-tenant1"], {"id-" + email for email in TENANT_ACCOUNTS})
        self.assertEqual(keycloak.members["org-other"], set())

    def test_an_account_without_tenant_roles_joins_no_organization(self):
        keycloak = FakeKeycloak(json.loads(REALM.read_text())["passwordPolicy"])
        self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        joined = set().union(*keycloak.members.values())
        self.assertNotIn("id-inceleme-press@example.test", joined)
        self.assertNotIn("id-inceleme-yerel-yonetici", joined)

    def test_a_repeated_run_keeps_the_members_and_does_not_fail(self):
        keycloak = FakeKeycloak(json.loads(REALM.read_text())["passwordPolicy"])
        keycloak.members["org-tenant1"] = {"id-inceleme-yonetici@example.test"}
        self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        self.assertEqual(keycloak.members["org-tenant1"], {"id-" + email for email in TENANT_ACCOUNTS})

    def test_a_missing_tenant_organization_is_created_with_the_tenant_alias(self):
        keycloak = FakeKeycloak(json.loads(REALM.read_text())["passwordPolicy"])
        del keycloak.organizations["org-tenant1"], keycloak.members["org-tenant1"]
        self.script["apply"](self.payload(), caller_factory=lambda *_: keycloak)
        self.assertEqual(keycloak.organizations["org-tenant1"]["alias"], "tenant1")
        self.assertEqual(keycloak.members["org-tenant1"], {"id-" + email for email in TENANT_ACCOUNTS})

    def test_a_failed_membership_stops_the_script(self):
        keycloak = FakeKeycloak(json.loads(REALM.read_text())["passwordPolicy"])
        original = keycloak.__call__

        def failing(method, path, data=None):
            if path.endswith("/members") and method == "POST":
                return 403, None, {"error": "forbidden"}
            return original(method, path, data)

        with self.assertRaises(SystemExit):
            self.script["apply"](self.payload(), caller_factory=lambda *_: failing)

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


TENANT_SCRIPT = E2E / "preview" / "stack-review-tenant.py"
ISSUER = "http://identity.localhost:6700/realms/platform"


class Row:
    def __init__(self, role):
        self.role = role


class FakeUser:
    """The parts of a Frappe User document that the tenant review script uses."""

    def __init__(self, tenant, email=None, user_type="System User", roles=()):
        self.tenant = tenant
        self.email = email
        self.user_type = user_type
        self.roles = [Row(role) for role in roles]
        self.role_profiles = []
        self.flags = Mock()

    def set(self, field, rows):
        if field != "role_profiles":
            raise AssertionError(field)
        self.role_profiles = [row["role_profile"] for row in rows]

    def update(self, values):
        for key, value in values.items():
            setattr(self, key, value)

    def append(self, field, row):
        if field != "roles":
            raise AssertionError(field)
        self.roles.append(Row(row["role"]))

    def add_roles(self, *roles):
        self.roles.extend(Row(role) for role in roles)
        self.save()

    def save(self):
        self.tenant.users[self.email] = self
        self.tenant.saves.append(self.email)


class FakeTenant:
    """A tenant site with a role list and users, standing in for the `frappe` module."""

    def __init__(self, roles, profiles=(), link_type=True):
        self.role_names = set(roles)
        self.profile_names = set(profiles)
        self.link_type = link_type
        self.users = {}
        self.saves = []
        self.links = []
        # Reseller Customer Link rows by customer tenant, and the inserts and updates made.
        self.reseller_links = {}
        self.link_writes = []

    def insert_link(self, fields):
        doc = Mock()
        doc.insert.side_effect = lambda: (
            self.reseller_links.__setitem__(fields["customer_tenant"], dict(fields)),
            self.link_writes.append(("insert", fields["customer_tenant"])),
        )
        return doc

    def exists(self, doctype, name):
        if doctype == "Role":
            return name in self.role_names
        if doctype == "Role Profile":
            return name in self.profile_names
        if doctype == "User":
            return name in self.users
        if doctype == "DocType":
            return self.link_type and name == "Reseller Customer Link"
        raise AssertionError(f"Unexpected exists({doctype!r}, {name!r})")

    def get_value(self, doctype, filters, fields=None, **kwargs):
        if doctype == "Reseller Customer Link":
            row = self.reseller_links.get(filters["customer_tenant"])
            if row is None:
                return None
            return {"name": "link-" + row["customer_tenant"], **row}
        return None

    def set_value(self, doctype, name, values):
        if doctype != "Reseller Customer Link":
            raise AssertionError(doctype)
        customer = name.removeprefix("link-")
        self.reseller_links[customer].update(values)
        self.link_writes.append(("update", customer))

    def modules(self):
        tenant = self
        frappe = Mock(name="frappe")
        frappe.db.exists.side_effect = tenant.exists
        frappe.db.get_value.side_effect = tenant.get_value
        frappe.db.set_value.side_effect = tenant.set_value
        frappe.get_doc.side_effect = lambda doctype, name=None: (
            tenant.insert_link(doctype) if isinstance(doctype, dict) else tenant.users[name]
        )
        frappe.new_doc.side_effect = lambda doctype: FakeUser(tenant)
        frappe.get_roles.side_effect = lambda email: [row.role for row in tenant.users[email].roles]
        sign_in = Mock()
        sign_in.create_link.side_effect = lambda issuer, subject, email: tenant.links.append(email)
        identity = Mock(sign_in=sign_in)
        return {
            "frappe": frappe,
            "frappe.utils": Mock(),
            "platform_core": Mock(identity=identity),
            "platform_core.identity": identity,
            "platform_core.identity.sign_in": sign_in,
        }


def administrator(roles=("Tenant Admin",)):
    return {
        "email": "inceleme-yonetici@example.test", "subject": "sub-admin", "first_name": "Review",
        "last_name": "Administrator", "tenant_roles": list(roles), "employee": False,
        "user_type": "Website User",
    }


def panel_account(email, role):
    return {
        "email": email, "subject": "sub-" + email, "first_name": "Review", "last_name": "Panel Role",
        "tenant_roles": [role], "employee": False, "user_type": "Website User", "role_profile": role,
    }


ALL_ROLES = {*PANEL_ROLES.values(), "System Manager"}
ALL_PROFILES = set(PANEL_ROLES.values())


class TenantScriptTest(unittest.TestCase):
    """G-53: the tenant administrator is a Website User whose only role is “Tenant Admin”."""

    def run_script(self, tenant, accounts, links=None):
        modules = tenant.modules()
        stdin = Mock()
        payload = {"issuer": ISSUER, "accounts": accounts}
        if links is not None:
            payload["reseller_links"] = links
        with patch.dict("sys.modules", modules), patch("os.chdir"), \
                patch("json.load", return_value=payload), \
                patch("sys.stdin", stdin), patch("builtins.print"):
            runpy.run_path(str(TENANT_SCRIPT))["main"]()
        return modules["frappe"]

    def test_a_new_administrator_is_a_website_user_with_only_the_tenant_admin_role(self):
        tenant = FakeTenant({"Tenant Admin", "System Manager"})
        self.run_script(tenant, [administrator()])
        user = tenant.users["inceleme-yonetici@example.test"]
        self.assertEqual(user.user_type, "Website User")
        self.assertEqual([row.role for row in user.roles], ["Tenant Admin"])

    def test_an_existing_system_manager_administrator_becomes_a_website_user(self):
        tenant = FakeTenant({"Tenant Admin", "System Manager"})
        tenant.users["inceleme-yonetici@example.test"] = FakeUser(
            tenant, "inceleme-yonetici@example.test", "System User", ("System Manager",)
        )
        self.run_script(tenant, [administrator()])
        user = tenant.users["inceleme-yonetici@example.test"]
        self.assertEqual(user.user_type, "Website User")
        self.assertEqual([row.role for row in user.roles], ["Tenant Admin"])

    def test_a_missing_tenant_admin_role_stops_with_a_clear_error_and_changes_nobody(self):
        tenant = FakeTenant({"System Manager"})
        with self.assertRaises(SystemExit) as stopped:
            self.run_script(tenant, [administrator()])
        self.assertIn("Tenant Admin", str(stopped.exception.code))
        self.assertEqual(tenant.saves, [])
        self.assertEqual(tenant.users, {})

    def test_an_account_without_a_user_type_keeps_its_roles_and_type(self):
        tenant = FakeTenant({"Employee", "HR User", "Blogger"})
        tenant.users["inceleme-panel@example.test"] = FakeUser(
            tenant, "inceleme-panel@example.test", "System User", ("Blogger",)
        )
        panel = {
            "email": "inceleme-panel@example.test", "subject": "sub-panel", "first_name": "Review",
            "last_name": "Panel", "tenant_roles": ["Employee", "HR User"], "employee": False,
        }
        self.run_script(tenant, [panel])
        user = tenant.users["inceleme-panel@example.test"]
        self.assertEqual(user.user_type, "System User")
        self.assertEqual({row.role for row in user.roles}, {"Blogger", "Employee", "HR User"})



def sample_links():
    return [dict(link) for link in json.loads(ACCOUNTS.read_text())["reseller_links"]]


class PanelRoleAccountsTest(unittest.TestCase):
    """G-168, G-169, G-170: four panel role accounts and two resellers with one customer each."""

    run_script = TenantScriptTest.run_script

    def accounts(self):
        return [panel_account(email, role) for email, role in PANEL_ROLES.items()]

    def test_each_account_is_a_website_user_with_its_role_profile_and_only_its_role(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES)
        self.run_script(tenant, self.accounts(), sample_links())
        for email, role in PANEL_ROLES.items():
            with self.subTest(email=email):
                user = tenant.users[email]
                self.assertEqual(user.user_type, "Website User")
                self.assertEqual(user.role_profiles, [role])
                self.assertEqual([row.role for row in user.roles], [role])

    def test_an_earlier_system_manager_role_is_taken_away_from_every_account(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES)
        for email in PANEL_ROLES:
            tenant.users[email] = FakeUser(tenant, email, "System User", ("System Manager",))
        self.run_script(tenant, self.accounts(), sample_links())
        for email in PANEL_ROLES:
            with self.subTest(email=email):
                self.assertNotIn("System Manager", [row.role for row in tenant.users[email].roles])

    def test_a_missing_role_profile_stops_before_any_change(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES - {"Reseller Assistant"})
        with self.assertRaises(SystemExit) as stopped:
            self.run_script(tenant, self.accounts(), sample_links())
        self.assertIn("Reseller Assistant", str(stopped.exception.code))
        self.assertEqual(tenant.saves, [])
        self.assertEqual(tenant.link_writes, [])

    def test_a_tenant_without_the_link_type_stops_before_any_change(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES, link_type=False)
        with self.assertRaises(SystemExit) as stopped:
            self.run_script(tenant, self.accounts(), sample_links())
        self.assertIn("Reseller Customer Link", str(stopped.exception.code))
        self.assertEqual(tenant.saves, [])

    def test_each_reseller_gets_only_its_own_sample_customer(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES)
        links = sample_links()
        self.run_script(tenant, self.accounts(), links)
        self.assertEqual(
            {customer: row["reseller_tenant"] for customer, row in tenant.reseller_links.items()},
            {link["customer_tenant"]: link["reseller_tenant"] for link in links},
        )

    def test_a_second_run_changes_nothing_and_does_not_fail(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES)
        self.run_script(tenant, self.accounts(), sample_links())
        first = {email: ([row.role for row in user.roles], user.role_profiles, user.user_type)
                 for email, user in tenant.users.items()}
        links = {customer: dict(row) for customer, row in tenant.reseller_links.items()}
        writes = list(tenant.link_writes)
        self.run_script(tenant, self.accounts(), sample_links())
        second = {email: ([row.role for row in user.roles], user.role_profiles, user.user_type)
                  for email, user in tenant.users.items()}
        self.assertEqual(second, first)
        self.assertEqual(tenant.reseller_links, links)
        self.assertEqual(tenant.link_writes, writes)

    def test_a_changed_link_in_the_file_updates_its_row(self):
        tenant = FakeTenant(ALL_ROLES, ALL_PROFILES)
        links = sample_links()
        self.run_script(tenant, self.accounts(), links)
        changed = [dict(link) for link in links]
        changed[0]["site_status"] = "Suspended"
        self.run_script(tenant, self.accounts(), changed)
        self.assertEqual(tenant.reseller_links[changed[0]["customer_tenant"]]["site_status"], "Suspended")
        self.assertEqual(tenant.link_writes[-1], ("update", changed[0]["customer_tenant"]))


if __name__ == "__main__":
    unittest.main()
