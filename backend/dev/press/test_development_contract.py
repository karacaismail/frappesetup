"""Check the disposable Press build and site setup contract."""

import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, Mock, patch

PRESS_DEV = Path(__file__).resolve().parent
REPO = PRESS_DEV.parents[2]


class ImageContractTest(unittest.TestCase):
    def test_readme_python_matches_shared_press_image_tag(self):
        decision = (REPO / "backend/docs/decisions/0009-naming-history-fix.md").read_text()
        image = re.search(r"`fs-press-tr-base:py(?P<version>\d+\.\d+\.\d+)`", decision)
        self.assertIsNotNone(image)
        readme = (PRESS_DEV / "README.md").read_text()
        versions = re.findall(r"(?m)^.*\bPython\b.* (\d+\.\d+\.\d+)\.$", readme)
        self.assertEqual(versions, [image["version"]])

    def test_site_setup_refreshes_hooks_after_press_install(self):
        commands = (PRESS_DEV / "install.sh").read_text().splitlines()
        install = commands.index("bench --site press.localhost install-app press_tr")
        disable_scheduler = commands.index("bench --site press.localhost disable-scheduler")
        self.assertLess(install, disable_scheduler)
        self.assertIn(
            "bench --site press.localhost execute frappe.cache.delete_value "
            """--args '[["all_apps", "app_hooks"]]'""",
            commands[disable_scheduler + 1 :],
        )

    def test_oidc_dependency_is_declared_and_bundled(self):
        metadata = (REPO / "backend/apps/press_tr/pyproject.toml").read_text()
        dockerfile = (PRESS_DEV / "Dockerfile").read_text()
        install = (PRESS_DEV / "install.sh").read_text()
        self.assertRegex(metadata, r'"oidc_verify[<>=~][^"]+"')
        self.assertIn("backend/libs/oidc_verify", dockerfile)
        self.assertIn("--wheel", dockerfile)
        self.assertIn("/opt/press-local/wheels/oidc_verify-*.whl", install)

    def test_runtime_artifact_is_named_for_its_contents(self):
        dockerfile = (PRESS_DEV / "Dockerfile").read_text()
        self.assertIn("AS runtime-check", dockerfile)
        self.assertNotIn("AS production", dockerfile)

    def test_runtime_oidc_install_is_offline_and_requires_hash(self):
        installer = PRESS_DEV / "install_runtime_oidc.sh"
        self.assertTrue(installer.is_file())
        text = installer.read_text()
        for option in ("--no-index", "--find-links", "--require-hashes"):
            self.assertIn(option, text)

    def test_compose_profile_is_configurable(self):
        self.assertIn("FS_COLIMA_PROFILE", (PRESS_DEV / "compose.sh").read_text())

    def test_direct_runtime_dependencies_are_declared(self):
        metadata = (REPO / "backend/apps/press_tr/pyproject.toml").read_text()
        dependencies = re.search(r"(?ms)^dependencies = \[(.*?)^\]", metadata).group(1)
        for name in ("oidc_verify", "packaging", "redis", "requests", "Werkzeug"):
            with self.subTest(name=name):
                self.assertRegex(dependencies, rf'(?i)"{name}(?=[<>=~"])')

    def test_bootstrap_uses_the_pinned_image_python(self):
        self.assertIn(
            ".pyenv/versions/3.14.10/bin/python3",
            (PRESS_DEV / "install.sh").read_text(),
        )

    def test_patch_is_excluded_from_production_stage(self):
        dockerfile = (PRESS_DEV / "Dockerfile").read_text()
        self.assertIn("AS runtime-check", dockerfile)
        self.assertIn("AS development", dockerfile)
        production, development = dockerfile.split("AS development", 1)
        self.assertNotIn("patch-py314.sh", production)
        self.assertIn("patch-py314.sh", development)
        if Path("/opt/press-local/development-image").is_file():
            self.skipTest("The patch must not be executed in a development image.")
        result = subprocess.run(
            ["bash", str(PRESS_DEV / "patch-py314.sh")], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("development image", result.stderr)

    @unittest.skipUnless(os.getenv("PRESS_TEST_RUNTIME_IMAGE"), "Set PRESS_TEST_RUNTIME_IMAGE")
    def test_runtime_check_image_rejects_the_patch(self):
        image = os.environ["PRESS_TEST_RUNTIME_IMAGE"]
        context = {"factory": "colima-factory", "default": "colima"}[
            os.getenv("FS_COLIMA_PROFILE", "factory")
        ]
        docker = ["docker", "--context", context, "run", "--rm", "--network", "none"]
        self.assertEqual(
            subprocess.run(
                [
                    *docker,
                    "--entrypoint",
                    "sh",
                    image,
                    "-ec",
                    "test ! -e /opt/press-local/development-image; "
                    "test ! -e /opt/press-local/scripts/patch-py314.sh; "
                    "test -r /opt/press-local/wheels/oidc_verify-0.1.0-py3-none-any.whl",
                ],
                check=False,
            ).returncode,
            0,
        )
        result = subprocess.run(
            [*docker, "-i", "--entrypoint", "bash", image, "-s"],
            input=(PRESS_DEV / "patch-py314.sh").read_text(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("development image", result.stderr)

    @unittest.skipUnless(os.getenv("PRESS_TEST_CLEAN_SOURCE"), "Set PRESS_TEST_CLEAN_SOURCE")
    def test_release_press_source_contains_no_development_patch(self):
        source = Path(os.environ["PRESS_TEST_CLEAN_SOURCE"])
        result = subprocess.run(
            ["git", "-C", str(source), "grep", "--untracked", "-n", "press-local:"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_passwords_are_mounted_as_compose_secrets(self):
        compose = (PRESS_DEV.parent / "compose.press.yaml").read_text()
        self.assertIn("MARIADB_ROOT_PASSWORD_FILE: /run/secrets/press_db_password", compose)
        self.assertNotRegex(compose, r"(?m)^ +PRESS_(?:DB|ADMIN)_PASSWORD:")
        self.assertIn("environment: PTR_DB_PASSWORD", compose)

    def test_bootstrap_does_not_pass_passwords_on_the_command_line(self):
        install = (PRESS_DEV / "install.sh").read_text()
        self.assertNotRegex(install, r"--(?:mariadb-root|db-root|admin)-password")
        create_site = (PRESS_DEV / "create_site.py").read_text()
        for variable in ("PTR_DB_PASSWORD", "PTR_ADMIN_PASSWORD"):
            self.assertIn(f'read_site_password("{variable}"', create_site)
        self.assertNotRegex(create_site, r"subprocess|sys\.argv")

    def test_site_bootstrap_hands_environment_credentials_to_frappe(self):
        frappe = ModuleType("frappe")
        frappe.init = Mock()
        frappe.destroy = Mock()
        frappe.database = ModuleType("frappe.database")
        frappe.database.get_command = Mock()
        installer = ModuleType("frappe.installer")
        installer._new_site = Mock()
        utils = ModuleType("frappe.utils")
        utils.CallbackManager = Mock()
        with (
            patch.dict(sys.modules, {"frappe": frappe, "frappe.installer": installer, "frappe.utils": utils}),
            patch.dict(os.environ, {"PTR_DB_PASSWORD": "db-fixture", "PTR_ADMIN_PASSWORD": "admin-fixture"}),
            patch("tempfile.NamedTemporaryFile"),
        ):
            runpy.run_path(str(PRESS_DEV / "create_site.py"), run_name="__main__")
        frappe.init.assert_called_once_with("press.localhost", new_site=True)
        kwargs = installer._new_site.call_args.kwargs
        self.assertEqual(kwargs["db_root_password"], "db-fixture")
        self.assertEqual(kwargs["admin_password"], "admin-fixture")
        self.assertEqual(kwargs["install_apps"], ["press"])
        frappe.destroy.assert_called_once()

    def test_generated_site_database_password_is_not_in_import_arguments(self):
        frappe = ModuleType("frappe")
        frappe.init = Mock()
        frappe.destroy = Mock()
        frappe.database = ModuleType("frappe.database")
        original = Mock(return_value=("mariadb", ["--user=fixture", "fixture-db"], "mariadb"))
        frappe.database.get_command = original
        installer = ModuleType("frappe.installer")
        utils = ModuleType("frappe.utils")
        utils.CallbackManager = Mock()
        option_file = MagicMock()
        option_file.name = "/fixture/press-db.cnf"
        handle = MagicMock()
        handle.__enter__.return_value = option_file

        def create_fixture(**kwargs):
            _, arguments, _ = frappe.database.get_command(user="fixture", password="generated-fixture")
            self.assertEqual(arguments[0], "--defaults-extra-file=/fixture/press-db.cnf")
            self.assertNotIn("generated-fixture", " ".join(arguments))
            option_file.write.assert_called_once_with('[client]\npassword="generated-fixture"\n')

        installer._new_site = create_fixture
        with (
            patch.dict(sys.modules, {"frappe": frappe, "frappe.installer": installer, "frappe.utils": utils}),
            patch.dict(os.environ, {"PTR_DB_PASSWORD": "db-fixture", "PTR_ADMIN_PASSWORD": "admin-fixture"}),
            patch("tempfile.NamedTemporaryFile", return_value=handle),
        ):
            runpy.run_path(str(PRESS_DEV / "create_site.py"), run_name="__main__")
        original.assert_called_once_with(user="fixture", password=None)
        self.assertIs(frappe.database.get_command, original)
        handle.__exit__.assert_called_once()


class ComposeContractTest(unittest.TestCase):
    @staticmethod
    def service_definition(service):
        manifest = (PRESS_DEV.parent / "compose.press.yaml").read_text()
        match = re.search(rf"^  {service}:\n((?:^ {{4,}}.*\n)+)", manifest, re.MULTILINE)
        if match is None:
            raise AssertionError(f"Missing Compose service: {service}")
        return match.group(1)

    def test_config_contract_runs_with_an_empty_docker_configuration(self):
        with (
            tempfile.TemporaryDirectory(dir=os.environ.get("PANE_SCRATCH_DIR")) as home,
            patch.dict(os.environ, {"HOME": home, "DOCKER_CONFIG": home}),
        ):
            self.assertEqual(self.compose_invocation(4250)["PTR_WEB_PORT"], "4253")

    def compose_invocation(self, port):
        env_file = PRESS_DEV / ".env.example"
        with tempfile.TemporaryDirectory(dir=os.environ.get("PANE_SCRATCH_DIR")) as bin_dir:
            # Capture the wrapper's real arguments without a host Docker profile or plugin.
            docker = Path(bin_dir) / "docker"
            docker.write_text(
                '#!/bin/sh\nexec "$PRESS_TEST_PYTHON" -c \''
                "import json, os, sys; "
                'print(json.dumps(dict(args=sys.argv[1:], PTR_WEB_PORT=os.environ["PTR_WEB_PORT"], '
                'PTR_SOCKET_PORT=os.environ["PTR_SOCKET_PORT"])))'
                '\' "$@"\n'
            )
            docker.chmod(0o755)
            env = {
                **os.environ,
                "PATH": bin_dir + os.pathsep + os.environ.get("PATH", os.defpath),
                "PRESS_TEST_PYTHON": sys.executable,
                "FS_COLIMA_PROFILE": "factory",
                "PANE_PORT": str(port),
                "PRESS_ENV_FILE": str(env_file),
                "PTR_WEB_PORT": "1",
                "PTR_SOCKET_PORT": "2",
            }
            result = subprocess.run(
                ["bash", str(PRESS_DEV / "compose.sh"), "config", "--format", "json"],
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = json.loads(result.stdout)
        self.assertEqual(
            invocation["args"],
            [
                "--context",
                "colima-factory",
                "compose",
                "--env-file",
                str(env_file),
                "--file",
                str(PRESS_DEV / "../compose.press.yaml"),
                "config",
                "--format",
                "json",
            ],
        )
        return invocation

    def test_ports_are_derived_from_the_pane_port(self):
        web = self.service_definition("web")
        ports = re.search(r"^    ports:\n((?:^      - .+\n)+)", web, re.MULTILINE)
        self.assertIsNotNone(ports)
        self.assertCountEqual(
            ports.group(1).splitlines(),
            [
                '      - "127.0.0.1:${PTR_WEB_PORT}:${PTR_WEB_PORT}"',
                '      - "127.0.0.1:${PTR_SOCKET_PORT}:${PTR_SOCKET_PORT}"',
            ],
        )
        for variable in ("PTR_WEB_PORT", "PTR_SOCKET_PORT"):
            self.assertRegex(web, rf"(?m)^      {variable}: \$\{{{variable}:\?[^}}]+\}}$")
        for port in (4250, 4310):
            with self.subTest(port=port):
                invocation = self.compose_invocation(port)
                self.assertEqual(invocation["PTR_WEB_PORT"], str(port + 3))
                self.assertEqual(invocation["PTR_SOCKET_PORT"], str(port + 4))

    def test_external_images_are_pinned_and_web_uses_the_development_target(self):
        for service in ("mariadb", "redis"):
            self.assertRegex(self.service_definition(service), r"(?m)^    image: \S+@sha256:[0-9a-f]{64}$")
        self.assertRegex(
            self.service_definition("web"), r"(?m)^    build:\n(?:^      .+\n)*^      target: development$"
        )
        dockerfile = (PRESS_DEV / "Dockerfile").read_text()
        self.assertRegex(dockerfile, re.compile(r"^FROM \S+@sha256:[0-9a-f]{64} AS \w+$", re.MULTILINE))


@unittest.skipUnless(shutil.which("docker"), "Docker Compose is required")
class UnpatchedComposeContractTest(unittest.TestCase):
    def config(self, with_port=False):
        docker_path = shutil.which("docker")
        self.assertIsNotNone(docker_path)
        process_env = {name: setting for name, setting in os.environ.items() if name != "PANE_PORT"}
        if with_port:
            process_env["PANE_PORT"] = "47320"
        completed = subprocess.run(
            [
                docker_path,
                "--context",
                "colima-factory",
                "compose",
                "-f",
                str(PRESS_DEV / "compose.unpatched.yaml"),
                "config",
                "--format",
                "json",
            ],
            env=process_env,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_probe_does_not_require_or_publish_a_port(self):
        probe = self.config()["services"]["probe"]
        self.assertNotIn("PANE_PORT", probe.get("environment", {}))
        self.assertNotIn("ports", probe)
        self.assertEqual(probe["network_mode"], "none")

    def test_probe_never_pulls_a_missing_local_image(self):
        self.assertEqual(self.config(with_port=True)["services"]["probe"].get("pull_policy"), "never")

    def test_probe_project_uses_the_assigned_task_name(self):
        self.assertEqual(self.config(with_port=True)["name"], "fs-pd-press-py314")
