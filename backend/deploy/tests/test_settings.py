"""Tests for the production setting lists (blocker E-4) and their server side check.

Two kinds of tests:
- The lists are complete: every production setting the code reads is in a list. The tests scan
  the code; a new setting without a list line fails here.
- remote/settings.py refuses an environment with a missing, empty or placeholder setting before
  anything changes on the server.
Design: backend/docs/dagitim/ortamlar.md, section "Üretim ayarları".
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
BACKEND = DEPLOY.parent
SETTINGS = DEPLOY / "settings"
sys.path.insert(0, str(DEPLOY))
sys.path.insert(0, str(DEPLOY / "remote"))
# remote/ is copied to the server as it is; keep it free of __pycache__.
sys.dont_write_bytecode = True

import release  # noqa: E402
import settings  # noqa: E402

REALM = BACKEND / "identity" / "keycloak" / "realm" / "platform-realm.json"
JAVA = BACKEND / "identity" / "keycloak" / "event-listener" / "src" / "main"
IDENTITY_SYNC_CONFIG = BACKEND / "identity" / "identity_sync" / "identity_sync" / "config.py"
IDENTITY_SYNC_IMAGE = BACKEND / "identity" / "identity_sync" / "Dockerfile"
STACK = DEPLOY / "compose" / "stack.yaml"
EDGE = DEPLOY / "compose" / "edge.yaml"

# Compose variables that are not settings of the server: remote/apply writes them (release.env)
# or they keep their default on purpose.
RELEASE_ENV = {"ATONOTA_HEALTH_SITE", "COMPOSE_PROFILES"}
# Measured later (blocker E-8); the stack keeps its default until then.
COMPOSE_DEFAULT_ONLY = {"ATONOTA_GUNICORN_WORKERS"}
# Variables of the remote scripts that are not settings: test paths and the first install switch.
SCRIPT_CONTROLS = {"ATONOTA_ROOT", "ATONOTA_ETC", "ATONOTA_FIRST_INSTALL"}


def listed(name):
    return {entry.key for entry in settings.parse_list(SETTINGS / settings.LISTS[name].list_file)}


def required(name):
    return {entry.key for entry in settings.parse_list(SETTINGS / settings.LISTS[name].list_file)
            if not entry.optional}


def _strings(node, scope):
    """String values a name or literal can hold: literals, module constants and literal tuples."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name) and node.id in scope:
        return _strings(scope[node.id], scope)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return set().union(*(_strings(item, scope) for item in node.elts)) if node.elts else set()
    return None


def _loop_values(target, source, name, scope):
    """Values that loop variable `name` takes in `for target in source` (tuples unpack by position)."""
    if isinstance(source, ast.Name) and source.id in scope:
        source = scope[source.id]
    if not isinstance(source, (ast.Tuple, ast.List, ast.Set)):
        return None
    if isinstance(target, ast.Name) and target.id == name:
        return _strings(source, scope)
    if isinstance(target, ast.Tuple):
        positions = [index for index, item in enumerate(target.elts)
                     if isinstance(item, ast.Name) and item.id == name]
        if positions and all(isinstance(row, ast.Tuple) and len(row.elts) == len(target.elts)
                             for row in source.elts):
            values = set()
            for row in source.elts:
                found = _strings(row.elts[positions[0]], scope)
                if found is None:
                    return None
                values |= found
            return values
    return None


def _resolve(name_node, parents, tree, scope):
    """Keys a conf read through a variable can read, or None when the scan cannot tell."""
    name = name_node.id
    if name in scope:
        return _strings(scope[name], scope)
    for parent in reversed(parents):
        if isinstance(parent, (ast.For, ast.comprehension)):
            values = _loop_values(parent.target, parent.iter, name, scope)
            if values is not None:
                return values
        if isinstance(parent, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            for generator in parent.generators:
                values = _loop_values(generator.target, generator.iter, name, scope)
                if values is not None:
                    return values
        if isinstance(parent, ast.FunctionDef) and name in [arg.arg for arg in parent.args.args]:
            position = [arg.arg for arg in parent.args.args].index(name)
            values = set()
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == parent.name]
            for call in calls:
                if position >= len(call.args):
                    return None
                found = _strings(call.args[position], scope)
                if found is None:
                    return None
                values |= found
            return values if calls else None
    return None


def site_reads(app_folder):
    """Every site_config key read by the Python code of one app.

    Read forms: frappe.conf.get(...), frappe.conf.x, frappe.conf[...], frappe.local.conf[...],
    getattr(frappe.conf, ...), frappe.get_site_config() and frappe.get_conf(). A key held in a
    variable is resolved from module constants, literal loops and the calls of the function.
    A read the scan cannot resolve is returned in `unresolved`, and the tests fail on it.
    """
    keys, unresolved = set(), []
    for path in sorted(app_folder.rglob("*.py")):
        relative = path.relative_to(app_folder).as_posix()
        if "/tests/" in f"/{relative}" or path.name.startswith("test_") or "contract_tests" in relative:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scope = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name)}
        conf_names = {"conf"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) and node.value.attr == "conf":
                conf_names.update(target.id for target in node.targets if isinstance(target, ast.Name))

        def is_conf(node):
            if isinstance(node, ast.Attribute) and node.attr == "conf":
                return True
            if isinstance(node, ast.Name) and node.id in conf_names:
                return True
            return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("get_site_config", "get_conf"))

        def add(argument, parents):
            if isinstance(argument, ast.Name):
                found = _resolve(argument, parents, tree, scope)
            else:
                found = _strings(argument, scope)
            if found:
                keys.update(found)
            else:
                unresolved.append((relative, getattr(argument, "lineno", 0)))

        def visit(node, parents):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
                    and is_conf(node.func.value) and node.args:
                add(node.args[0], parents)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr" \
                    and len(node.args) >= 2 and is_conf(node.args[0]):
                add(node.args[1], parents)
            elif isinstance(node, ast.Subscript) and is_conf(node.value):
                add(node.slice, parents)
            elif isinstance(node, ast.Attribute) and is_conf(node.value) and node.attr not in ("get", "conf"):
                keys.add(node.attr)
            for child in ast.iter_child_nodes(node):
                visit(child, [*parents, node])

        visit(tree, [])
    return keys, unresolved


class ListFiles(unittest.TestCase):
    def test_every_list_exists_and_parses(self):
        for name, target in settings.LISTS.items():
            with self.subTest(name=name):
                entries = settings.parse_list(SETTINGS / target.list_file)
                self.assertTrue(target.list_file.endswith(".production.env.example"), target.list_file)
                keys = [entry.key for entry in entries]
                self.assertEqual(len(keys), len(set(keys)), f"{name}: a key is listed twice")

    def test_settings_folder_holds_only_the_registered_lists(self):
        present = {path.name for path in SETTINGS.iterdir()}
        self.assertEqual(present, {target.list_file for target in settings.LISTS.values()})

    def test_keycloak_list_is_the_one_of_the_keycloak_folder(self):
        # One list only: the Keycloak tests read identity/keycloak/production.env.example too.
        link = SETTINGS / settings.LISTS["keycloak"].list_file
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (BACKEND / "identity" / "keycloak" / "production.env.example").resolve())

    def test_secret_values_are_placeholders(self):
        # The repository holds no real secret: a secret line shows only the expected form.
        for name, target in settings.LISTS.items():
            for entry in settings.parse_list(SETTINGS / target.list_file):
                if re.search(r"(?i)(secret|password|passwd|token|key)(?:_|$)", entry.key) and not entry.fixed:
                    with self.subTest(name=name, key=entry.key):
                        self.assertTrue(settings.is_placeholder(entry.value), entry.value)

    def test_every_secret_file_of_the_stack_has_a_list(self):
        files = set(re.findall(r'/etc/atonota/\$\{ATONOTA_ENV:\?\}/([a-z-]+)\.env', STACK.read_text()))
        self.assertTrue(files)
        targets = {Path(target.path).name for target in settings.LISTS.values() if target.kind == "env"}
        for name in sorted(files):
            self.assertIn(f"{name}.env", targets, name)


class CodeScan(unittest.TestCase):
    """A setting read by the code and missing from its list fails here."""

    def test_keycloak_realm_placeholders(self):
        names = re.findall(r"\$\{([A-Z0-9_]+)(:[^}]*)?\}", REALM.read_text())
        self.assertTrue(names)
        # A turned off login provider (Google, Apple) may stay without its values. Once a
        # provider is turned on in the realm, its values become required here.
        switched_off = {
            name
            for provider in json.loads(REALM.read_text()).get("identityProviders", [])
            if not provider.get("enabled")
            for value in provider.get("config", {}).values()
            for name in re.findall(r"\$\{([A-Z0-9_]+)\}", str(value))
        }
        for name, default in names:
            with self.subTest(name=name):
                self.assertIn(name, listed("keycloak"))
                if not default and name not in switched_off:
                    self.assertIn(name, required("keycloak"))

    def test_keycloak_extension_settings(self):
        found = set()
        for path in JAVA.rglob("*.java"):
            text = path.read_text()
            options = re.findall(r'config\.get\("([a-zA-Z0-9-]+)"\)', text)
            if not options:
                continue
            if "implements EventListenerProviderFactory" not in text:
                self.fail(f"{path.name} reads SPI settings of an unknown SPI type; extend this test")
            provider = re.search(r'String ID = "([a-z0-9-]+)"', text).group(1)
            for option in options:
                found.add(f"KC_SPI_EVENTS_LISTENER__{provider.upper()}__{option.upper()}")
        self.assertTrue(found)
        self.assertLessEqual(found, listed("keycloak"))

    def test_keycloak_database_and_bootstrap_settings(self):
        # stack.yaml gives Keycloak the database host and user; the password and the first admin
        # come from keycloak.env. keycloak-db.env gives PostgreSQL the same user and password.
        self.assertIn("KC_DB_USERNAME: keycloak", STACK.read_text())
        self.assertLessEqual({"KC_DB_PASSWORD", "KC_BOOTSTRAP_ADMIN_USERNAME", "KC_BOOTSTRAP_ADMIN_PASSWORD"},
                             required("keycloak"))
        self.assertLessEqual({"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}, required("keycloak-db"))

    def test_identity_sync_settings(self):
        source = IDENTITY_SYNC_CONFIG.read_text()
        names = set(re.findall(r'\bget\("([A-Z_]+)"', source))
        required_block = re.search(r"required = \((.*?)\)", source, re.S).group(1)
        needed = set(re.findall(r'"([A-Z_]+)"', required_block))
        self.assertTrue(needed)
        image = set(re.findall(r"\b(IDENTITY_SYNC_[A-Z_]+)=", IDENTITY_SYNC_IMAGE.read_text()))
        for name in sorted(names | needed):
            key = f"IDENTITY_SYNC_{name}"
            with self.subTest(key=key):
                if key in image:
                    continue  # the image sets it (host, port, database path)
                self.assertIn(key, listed("identity-sync"))
                if name in needed:
                    self.assertIn(key, required("identity-sync"))

    def check_site_list(self, list_name, apps):
        keys, unresolved = set(), []
        for app in apps:
            found, missing = site_reads(BACKEND / "apps" / app)
            keys |= found
            unresolved += missing
        self.assertEqual(unresolved, [], "the scan cannot tell which key these reads use; name the key")
        self.assertTrue(keys)
        for key in sorted(keys):
            with self.subTest(key=key):
                self.assertIn(key, listed(list_name))

    def test_scan_finds_every_read_form(self):
        # A read the scan misses would leave a setting out of the lists (review 1, finding 4).
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / "module.py").write_text(
                "import frappe\n"
                "NAME = 'from_constant'\n"
                "PAIRS = (('from_module_tuple', 1),)\n"
                "a = frappe.conf.get('from_get')\n"
                "b = frappe.conf.from_attribute\n"
                "c = frappe.conf['from_subscript']\n"
                "d = frappe.local.conf['from_local']\n"
                "e = getattr(frappe.conf, 'from_getattr')\n"
                "f = frappe.get_site_config().get('from_site_config')\n"
                "g = frappe.get_conf()['from_get_conf']\n"
                "h = frappe.conf.get(NAME)\n"
                "def read(setting):\n"
                "    return frappe.conf.get(setting)\n"
                "read('from_parameter')\n"
                "for key, _ in (('from_loop', 1), ('from_loop_two', 2)):\n"
                "    frappe.conf.get(key)\n"
                "for key, _ in PAIRS:\n"
                "    frappe.conf.get(key)\n"
                "missing = [key for key in ('from_comprehension',) if not frappe.conf.get(key)]\n")
            keys, unresolved = site_reads(app)
        self.assertEqual(unresolved, [])
        self.assertEqual(keys, {
            "from_constant", "from_module_tuple", "from_get", "from_attribute", "from_subscript", "from_local",
            "from_getattr", "from_site_config", "from_get_conf", "from_parameter", "from_loop", "from_loop_two",
            "from_comprehension",
        })

    def test_unresolved_read_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / "module.py").write_text("import frappe\ndef f(name):\n    return frappe.conf.get(name)\n")
            _, unresolved = site_reads(app)
        self.assertEqual(len(unresolved), 1)

    def test_tenant_site_settings(self):
        self.check_site_list("tenant-site", ("platform_core", "hrms_tr"))

    def test_tenant_site_identity_settings_are_required(self):
        # site_settings.REQUIRED stops the login when one is missing.
        source = (BACKEND / "apps/platform_core/platform_core/identity/site_settings.py").read_text()
        block = re.search(r"REQUIRED = \((.*?)\)", source, re.S).group(1)
        needed = set(re.findall(r'"([a-z_]+)"', block))
        self.assertTrue(needed)
        self.assertLessEqual(needed, required("tenant-site"))

    def test_press_site_settings(self):
        self.check_site_list("press-site", ("press_tr",))

    def test_compose_variables(self):
        known = release.ENV_KEYS | RELEASE_ENV | COMPOSE_DEFAULT_ONLY | listed("edge")
        for path in (STACK, EDGE):
            for name in re.findall(r"\$\{([A-Z0-9_]+)", path.read_text()):
                with self.subTest(file=path.name, name=name):
                    if name.startswith("ATONOTA_IMAGE_"):
                        continue  # release.env, from release.json
                    self.assertIn(name, known)
        self.assertIn("ATONOTA_ACME_EMAIL", required("edge"))

    def test_remote_script_variables(self):
        known = release.ENV_KEYS | SCRIPT_CONTROLS | listed("offsite")
        for path in sorted((DEPLOY / "remote").iterdir()):
            if path.suffix == ".py":
                continue
            for name in re.findall(r"\$\{?(ATONOTA_[A-Z0-9_]+)", path.read_text()):
                with self.subTest(file=path.name, name=name):
                    self.assertIn(name, known)
        self.assertIn("ATONOTA_OFFSITE_REMOTE", required("offsite"))

    def test_tenant_containers_reach_their_database_and_redis(self):
        # Frappe 16 reads these from the environment (frappe/config.py, node_utils.js); without
        # them the tenant processes look for the database on 127.0.0.1.
        self.assertLessEqual({"FRAPPE_DB_HOST", "FRAPPE_DB_PORT", "FRAPPE_REDIS_CACHE", "FRAPPE_REDIS_QUEUE"},
                             required("tenant"))
        self.assertIn("MARIADB_ROOT_PASSWORD", required("tenant-db"))


def run_python(*arguments, input_text=None, environment=None):
    """Run a deploy script with this Python, fixed arguments and no shell."""
    return subprocess.run([sys.executable, "-I", *map(str, arguments)], input=input_text,
                          env=environment, capture_output=True, text=True)


# Test values. Names held in variables keep the secret scanner from reading them as passwords.
EMPTY = ""
UNFILLED = "<identity-sync istemci sırrı>"
SITE_VALUE = "very-secret-value"


def write_env(path, values, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(mode)


def filled(name):
    """A complete file for one list: fixed values as listed, every other key a fake value."""
    values = {}
    for entry in settings.parse_list(SETTINGS / settings.LISTS[name].list_file):
        if entry.optional:
            continue
        values[entry.key] = entry.value if entry.fixed else "fake-value-for-tests-0123456789abcdef"
    return values


def fill_server(etc, env, press=False, offsite=False):
    """Write every secret file of one environment, as the DevOps owner does on the server."""
    for name, target in settings.LISTS.items():
        if target.kind != "env" or (target.when == "press" and not press) or (
                target.when == "offsite" and not offsite):
            continue
        write_env(Path(target.path.format(etc=etc, env=env)), filled(name))


class FileCheck(unittest.TestCase):
    def setUp(self):
        self.etc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.etc)

    def check(self, env="alpha", press=False, offsite=False):
        return settings.check_files(env, SETTINGS, self.etc, press=press, offsite_required=offsite)

    def test_complete_environment_passes(self):
        fill_server(self.etc, "alpha")
        self.assertEqual(self.check(), [])

    def test_missing_file_is_named(self):
        fill_server(self.etc, "alpha")
        (self.etc / "alpha" / "keycloak.env").unlink()
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(str(self.etc / "alpha" / "keycloak.env"), problems[0])
        self.assertIn("missing", problems[0])

    def test_missing_key_is_named_and_no_value_is_printed(self):
        fill_server(self.etc, "prod")
        values = filled("keycloak")
        del values["KC_DB_PASSWORD"]
        values["ATONOTA_SMTP_PASSWORD"] = EMPTY
        write_env(self.etc / "prod" / "keycloak.env", values)
        problems = self.check("prod")
        text = "\n".join(problems)
        self.assertIn("KC_DB_PASSWORD", text)
        self.assertIn("ATONOTA_SMTP_PASSWORD", text)
        self.assertNotIn("fake-value-for-tests", text)

    def test_placeholder_value_counts_as_missing(self):
        fill_server(self.etc, "alpha")
        values = filled("identity-sync")
        values["IDENTITY_SYNC_CLIENT_SECRET"] = UNFILLED
        write_env(self.etc / "alpha" / "identity-sync.env", values)
        problems = self.check()
        self.assertTrue(any("IDENTITY_SYNC_CLIENT_SECRET" in line and "placeholder" in line for line in problems))

    def test_fixed_value_must_match(self):
        fill_server(self.etc, "alpha")
        values = filled("keycloak")
        values["ATONOTA_SSL_REQUIRED"] = "external"
        write_env(self.etc / "alpha" / "keycloak.env", values)
        problems = self.check()
        self.assertTrue(any("ATONOTA_SSL_REQUIRED" in line and "all" in line for line in problems), problems)

    def test_optional_key_may_be_absent(self):
        fill_server(self.etc, "alpha")
        optional = [e.key for e in settings.parse_list(SETTINGS / settings.LISTS["keycloak"].list_file) if e.optional]
        self.assertIn("ATONOTA_APPLE_P8_KEY", optional)
        self.assertEqual(self.check(), [])

    def test_secret_file_readable_by_others_is_refused(self):
        fill_server(self.etc, "alpha")
        (self.etc / "alpha" / "tenant-db.env").chmod(0o644)
        problems = self.check()
        self.assertTrue(any("tenant-db.env" in line and "0600" in line for line in problems), problems)

    def test_press_file_is_needed_only_with_a_press_image(self):
        fill_server(self.etc, "rc")
        self.assertEqual(self.check("rc", press=False), [])
        problems = self.check("rc", press=True)
        self.assertTrue(any("press.env" in line for line in problems), problems)

    def test_offsite_file_follows_the_environment_rule(self):
        fill_server(self.etc, "prod")
        problems = self.check("prod", offsite=True)
        self.assertTrue(any("offsite.env" in line for line in problems), problems)
        # Without the rule the file is optional, but a present file must be complete.
        self.assertEqual(self.check("prod", offsite=False), [])
        write_env(self.etc / "prod" / "offsite.env", {"ATONOTA_OFFSITE_REMOTE": "offsite:backups"})
        problems = self.check("prod", offsite=False)
        self.assertTrue(any("RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY" in line for line in problems), problems)

    def test_edge_file_is_shared_by_the_server(self):
        fill_server(self.etc, "beta")
        (self.etc / "edge.env").unlink()
        problems = self.check("beta")
        self.assertTrue(any(str(self.etc / "edge.env") in line for line in problems), problems)

    def test_inline_comment_is_not_a_value(self):
        # docker compose drops " # ..." after an unquoted value (review 1, finding 3).
        fill_server(self.etc, "alpha")
        path = self.etc / "alpha" / "tenant-db.env"
        path.write_text("MARIADB_ROOT_PASSWORD= # later\n")
        path.chmod(0o600)
        self.assertIn(f"{path}: MARIADB_ROOT_PASSWORD (missing)", self.check())
        path.write_text("MARIADB_ROOT_PASSWORD=<kök parolası> # todo\n")
        self.assertIn(f"{path}: MARIADB_ROOT_PASSWORD (placeholder left)", self.check())
        path.write_text("MARIADB_ROOT_PASSWORD='abc # def'\n")
        self.assertEqual(self.check(), [])

    def test_dollar_sign_needs_single_quotes(self):
        # docker compose replaces $NAME in unquoted and double quoted values.
        fill_server(self.etc, "alpha")
        path = self.etc / "alpha" / "tenant-db.env"
        for line in ("MARIADB_ROOT_PASSWORD=ab$cd\n", 'MARIADB_ROOT_PASSWORD="ab$cd"\n'):
            path.write_text(line)
            path.chmod(0o600)
            problems = self.check()
            self.assertEqual(problems, [f"{path}: MARIADB_ROOT_PASSWORD (has $; write the value in single quotes)"])
            self.assertNotIn("ab$cd", "\n".join(problems))
        path.write_text("MARIADB_ROOT_PASSWORD='ab$cd'\n")
        self.assertEqual(self.check(), [])

    def test_command_line_exit_status(self):
        fill_server(self.etc, "alpha")
        script = DEPLOY / "remote" / "settings.py"
        command = [script, "check-files", "alpha", SETTINGS, "--etc", self.etc, "--press", "0", "--offsite", "0"]
        passed = run_python(*command)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        (self.etc / "alpha" / "tenant.env").unlink()
        failed = run_python(*command)
        self.assertEqual(failed.returncode, 1)
        self.assertIn("tenant.env", failed.stderr)


class SiteCheck(unittest.TestCase):
    SITE = "demo.app.alpha.atonota.net"

    def complete(self, differs=()):
        return {"set": sorted(required("tenant-site")), "differs": list(differs)}

    def test_complete_site_passes(self):
        self.assertEqual(settings.check_sites(SETTINGS, {self.SITE: self.complete()}, [self.SITE]), [])

    def test_missing_site_key_is_named(self):
        report = self.complete()
        report["set"].remove("keycloak_client_secret")
        problems = settings.check_sites(SETTINGS, {self.SITE: report}, [self.SITE])
        self.assertEqual(len(problems), 1)
        self.assertIn(self.SITE, problems[0])
        self.assertIn("keycloak_client_secret", problems[0])

    def test_missing_site_is_refused_after_the_first_install(self):
        problems = settings.check_sites(SETTINGS, {}, [self.SITE])
        self.assertTrue(any("does not exist" in line for line in problems), problems)
        self.assertEqual(settings.check_sites(SETTINGS, {}, [self.SITE], first_install=True), [])

    def test_fixed_site_values_are_the_safety_switches(self):
        # developer_mode=1 or mobile_allow_development_http=1 opens plain HTTP paths (review 1).
        fixed = settings.site_fixed_values(SETTINGS)
        self.assertEqual(fixed.get("developer_mode"), "0")
        self.assertEqual(fixed.get("mobile_allow_development_http"), "0")

    def test_site_value_that_differs_from_its_fixed_value_is_refused(self):
        report = self.complete(differs=["developer_mode"])
        problems = settings.check_sites(SETTINGS, {self.SITE: report}, [self.SITE])
        self.assertEqual(problems, [f"site {self.SITE}, site_config.json: developer_mode (must be 0)"])

    def test_bad_probe_answer_is_refused(self):
        with self.assertRaises(settings.SettingsError):
            settings.check_sites(SETTINGS, {self.SITE: ["keycloak_public_url"]}, [self.SITE])

    def probe(self, site_config, common=None):
        with tempfile.TemporaryDirectory() as folder:
            sites = Path(folder)
            (sites / self.SITE).mkdir()
            (sites / "common_site_config.json").write_text(json.dumps(common or {}))
            (sites / self.SITE / "site_config.json").write_text(json.dumps(site_config))
            result = run_python("-", "site-settings-probe", json.dumps(settings.site_fixed_values(SETTINGS)),
                                self.SITE, "absent.test",
                                input_text=(DEPLOY / "remote" / "site-probe.py").read_text(),
                                environment={**os.environ, "ATONOTA_SITES_PATH": folder})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(SITE_VALUE, result.stdout)
        return json.loads(result.stdout)

    def test_site_probe_prints_key_names_only(self):
        found = self.probe({"keycloak_client_secret": SITE_VALUE, "keycloak_realm": EMPTY, "x": "<yer tutucu>",
                            "mcp_oauth_enabled": 0}, common={"host_name": "https://x.test"})
        self.assertEqual(found, {self.SITE: {
            "set": ["host_name", "keycloak_client_secret", "mcp_oauth_enabled"], "differs": []}})

    def test_site_probe_compares_fixed_values_inside_the_container(self):
        found = self.probe({"mobile_allow_development_http": 1, "keycloak_client_id": SITE_VALUE},
                           common={"developer_mode": 1})
        self.assertEqual(found[self.SITE]["differs"], ["developer_mode", "mobile_allow_development_http"])
        self.assertEqual(self.probe({"developer_mode": 0})[self.SITE]["differs"], [])
        self.assertEqual(self.probe({"developer_mode": "0"})[self.SITE]["differs"], [])
        self.assertEqual(self.probe({"developer_mode": False})[self.SITE]["differs"], [])
        self.assertEqual(self.probe({"developer_mode": True})[self.SITE]["differs"], ["developer_mode"])

    def test_press_site_list_is_not_checked_until_the_press_image_exists(self):
        # E-2: no Press image, so no Press site to probe. The list waits; this test says so.
        self.assertEqual(settings.LISTS["press-site"].when, "press-image")
        self.assertIn("press-site", settings.NOT_CHECKED)


class Packing(unittest.TestCase):
    def test_release_carries_every_list(self):
        for target in settings.LISTS.values():
            self.assertIn(f"settings/{target.list_file}", release.NEEDED)
        self.assertIn("remote/settings.py", release.NEEDED)
        self.assertIn("remote/site-probe.py", release.NEEDED)


if __name__ == "__main__":
    unittest.main()
