"""The shared stack must isolate services and never expose credentials."""

import contextlib
import io
import json
import os
import re
import runpy
import secrets
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "backend/e2e/stack"
CONTAINER_ID = "0123456789ab"
# setup() derives the URLs. The credential file supplies the two fake client values.
PRESS_ENVIRONMENT = {
    "ATONOTA_PRESS_URL": "http://press.localhost:7153",
    "KC_PUBLIC_URL": "http://identity.localhost:7150",
    "ATONOTA_PRESS_SECRET": "fake-press-client-value",
    "ATONOTA_PRESS_SERVICE_SECRET": "fake-press-service-value",
}
# As in real use, the credential file also supplies the Keycloak admin login for the realm sync.
# The values are made at run time so no credential-like literal sits in the source.
PRESS_ENVIRONMENT.update(
    KC_BOOTSTRAP_ADMIN_USERNAME=secrets.token_hex(8),
    KC_BOOTSTRAP_ADMIN_PASSWORD=secrets.token_urlsafe(16),
)


class StackTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.env = dict(
            os.environ,
            PANE_PORT="7150",
            FS_COLIMA_PROFILE="factory",
            E2E_ENV_FILE=str(Path(self.temp.name) / ".env"),
        )
        self.project = runpy.run_path(str(STACK))["project_name"](self.env)

    def run_stack(self, action, **environment):
        return subprocess.run(
            ["python3.14", str(STACK), action],
            env=dict(self.env, **environment),
            capture_output=True,
            text=True,
        )

    def test_two_worktrees_and_ports_have_disjoint_compose_resources(self):
        self.assertEqual(self.run_stack("config").returncode, 0)
        namespace = runpy.run_path(str(STACK))
        models = []
        for folder in ("first", "second"):
            backend = Path(self.temp.name) / folder / "backend"
            (backend / "dev").mkdir(parents=True)
            for source in (ROOT / "backend/dev").glob("compose*.yaml"):
                shutil.copyfile(source, backend / "dev" / source.name)
            for port in ("7150", "7270"):
                with (
                    patch.dict(namespace["setup"].__globals__, {"BACKEND": backend}),
                    patch.dict(os.environ, dict(self.env, PANE_PORT=port)),
                ):
                    environment, _, compose = namespace["setup"]()
                    model = namespace["config"](compose, environment)
                    models.append(model)
                    again = namespace["setup"]()[2]
                    self.assertEqual(compose, again)
        names = [model["name"] for model in models]
        self.assertEqual(len(set(names)), 4, names)
        volumes = [{volume["name"] for volume in model["volumes"].values()} for model in models]
        images = [
            {
                service.get("image") or model["name"] + "-" + name
                for name, service in model["services"].items()
                if "build" in service
            }
            for model in models
        ]
        for index, model in enumerate(models):
            self.assertTrue(all(name.startswith(model["name"] + "_") for name in volumes[index]))
            for previous in volumes[:index]:
                self.assertTrue(volumes[index].isdisjoint(previous))
            self.assertTrue(all(model["name"] in name for name in images[index]))
            for previous in images[:index]:
                self.assertTrue(images[index].isdisjoint(previous))

    def test_invalid_realm_id_stops_before_receiver_or_bootstrap(self):
        namespace = runpy.run_path(str(STACK))
        for realm_id in ("", "first-id\nsecond-id\n", "invalid realm"):
            with self.subTest(realm_id=realm_id):
                environment = dict(PRESS_ENVIRONMENT)
                with (
                    patch.dict(
                        namespace["up"].__globals__,
                        {
                            "check_resources": lambda *args: None,
                            "config": lambda *args: {},
                            "ensure_images": lambda *args: None,
                        },
                    ),
                    patch(
                        "subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=realm_id)
                    ) as execute,
                ):
                    with self.assertRaisesRegex(ValueError, "one valid internal ID"):
                        namespace["up"](["docker"], ["compose"], environment)
                commands = [call.args[0] for call in execute.call_args_list]
                # Keycloak up, realm sync (T-11), realm ID query; nothing after the bad ID.
                self.assertEqual(len(commands), 3)
                self.assertEqual(commands[0][:2], ["compose", "up"])
                sync = ["compose", "run", "--rm", "--no-deps", "-T", "identity-sync"]
                self.assertEqual(commands[1][:6], sync)
                self.assertEqual(commands[-1][-1], "SELECT id FROM realm WHERE name = 'platform'")
                self.assertFalse(any(command[-1] == "identity-sync" for command in commands))
                self.assertFalse(any("/workspace/dev/bootstrap.py" in command for command in commands))
                self.assertNotIn("IDENTITY_SYNC_REALM_ID", environment)

    def test_standalone_compose_keeps_its_image_names(self):
        namespace = runpy.run_path(str(STACK))
        with patch.dict(os.environ, self.env):
            environment, _, compose = namespace["setup"]()
        environment.pop("FS_STACK_IMAGE_TAG")
        for fragment, expected in (
            ("tenant", {"tenant-web": "fs-tenant-dev:7150"}),
            (
                "keycloak",
                {"keycloak": "fs-keycloak-atonota:dev-7150", "event-sink": "fs-kimlik-realm-event-sink:dev"},
            ),
        ):
            command = [*compose[:-1], str(ROOT / "backend/dev" / f"compose.{fragment}.yaml")]
            model = namespace["config"](command, environment)
            for service, image in expected.items():
                self.assertEqual(model["services"][service]["image"], image)

    def test_isolated_owners_preserve_foreign_and_legacy_volumes(self):
        namespace = runpy.run_path(str(STACK))
        volumes = {"fs-e2e-ortam-owner": "legacy-owner", "fs-e2e-ortam_db": "legacy-data"}
        owners = []

        def docker(command, environment, **kwargs):
            if command[1] == "ps":
                output = ""
            elif command[1:3] == ["volume", "ls"]:
                output = "\n".join(volumes)
            elif command[1:3] == ["volume", "create"]:
                volumes[command[-1]] = command[-2].split("=", 1)[1]
                output = command[-1]
            elif command[1:3] == ["volume", "inspect"]:
                output = json.dumps([{"Labels": {"io.frappesetup.stack-owner": volumes[command[-1]]}}])
            else:
                self.fail(f"Unexpected mutation: {command}")
            return subprocess.CompletedProcess(command, 0, stdout=output)

        for folder in ("first", "second"):
            for port in ("7150", "7270"):
                backend = Path(self.temp.name) / folder / "backend"
                environment = {"PANE_PORT": port}
                compose = ["compose", "--env-file", self.env["E2E_ENV_FILE"]]
                with patch.dict(namespace["assert_owner"].__globals__, {"BACKEND": backend, "run": docker}):
                    namespace["assert_owner"](["docker"], compose, environment, create=True)
                    namespace["assert_owner"](["docker"], compose, environment)
                owners.append((backend, compose, environment))
        self.assertEqual(len(volumes), 6)
        self.assertEqual(volumes["fs-e2e-ortam-owner"], "legacy-owner")
        self.assertEqual(volumes["fs-e2e-ortam_db"], "legacy-data")
        backend, compose, environment = owners[-1]
        marker = next(reversed(volumes))
        volumes[marker] = "another-owner"
        before = dict(volumes)
        with patch.dict(namespace["assert_owner"].__globals__, {"BACKEND": backend, "run": docker}):
            with self.assertRaisesRegex(ValueError, "saved volumes belong"):
                namespace["assert_owner"](["docker"], compose, environment, create=True)
        self.assertEqual(volumes, before)

    def test_config_combines_services_and_loopback_ports(self):
        result = self.run_stack("config")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["name"], self.project)
        self.assertEqual(
            set(config["services"]),
            {
                "tenant-db",
                "tenant-redis",
                "tenant-web",
                "tenant-socket",
                "keycloak",
                "keycloak-db",
                "event-sink",
                "identity-sync",
                "mailpit",
                "web",
                "mariadb",
                "redis",
            },
        )
        ports = {
            port["published"] for service in config["services"].values() for port in service.get("ports", [])
        }
        self.assertEqual(ports, {str(7150 + offset) for offset in (0, 1, 2, 3, 4, 5, 6)})
        for service in config["services"].values():
            self.assertNotIn("environment", service)
            for port in service.get("ports", []):
                self.assertEqual(port["host_ip"], "127.0.0.1")
        path = Path(self.env["E2E_ENV_FILE"])
        original = path.read_bytes()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.run_stack("config").returncode, 0)
        self.assertEqual(path.read_bytes(), original)
        for line in original.decode().splitlines():
            key, value = line.split("=", 1)
            if "SECRET" in key or "PASSWORD" in key:
                self.assertNotIn(value, result.stdout + result.stderr)

    def test_invalid_port_and_profile_do_not_create_credentials(self):
        for values in (
            {"PANE_PORT": ""},
            {"PANE_PORT": "0010"},
            {"PANE_PORT": "65527"},
            {"FS_COLIMA_PROFILE": "other"},
        ):
            with self.subTest(values=values):
                self.assertEqual(self.run_stack("config", **values).returncode, 2)
        self.assertFalse(Path(self.env["E2E_ENV_FILE"]).exists())

    def test_listener_targets_real_identity_service_with_runtime_secret(self):
        module = runpy.run_path(str(STACK))
        with patch.dict(os.environ, self.env):
            environment, _, compose = module["setup"]()
        model = module["config"](compose, environment)
        services = model["services"]
        self.assertIn("identity-sync", set(services))
        receiver = services["identity-sync"]
        settings = receiver["environment"]
        listener = services["keycloak"]["environment"]
        self.assertEqual(
            listener["KC_SPI_EVENTS_LISTENER__WEBHOOK__URL"], "http://identity-sync.localhost:6115/v1/events"
        )
        self.assertTrue(settings["IDENTITY_SYNC_WEBHOOK_SECRET"])
        self.assertTrue(
            settings["IDENTITY_SYNC_WEBHOOK_SECRET"] == listener["KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET"]
        )
        self.assertEqual(settings["IDENTITY_SYNC_KEYCLOAK_PUBLIC_URL"], "http://identity.localhost:7150")
        self.assertEqual(receiver["ports"][0]["published"], "7155")
        self.assertEqual(receiver["ports"][0]["host_ip"], "127.0.0.1")
        self.assertNotIn("args", receiver["build"])

    def test_up_refreshes_listener_and_receiver_even_when_images_exist(self):
        module = runpy.run_path(str(STACK))
        services = {
            name: {"image": "local-test-" + name}
            for name in ("tenant-web", "keycloak", "event-sink", "web", "identity-sync")
        }
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as execute:
            module["ensure_images"](["docker"], ["compose"], {}, {"services": services})
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertIn(["compose", "build", "keycloak"], commands)
        self.assertIn(["compose", "build", "identity-sync"], commands)

    def test_rejects_public_credentials(self):
        path = Path(self.env["E2E_ENV_FILE"])
        path.write_text("SECRET=synthetic\n")
        path.chmod(0o644)
        self.assertNotEqual(self.run_stack("config").returncode, 0)
        self.assertEqual(path.read_text(), "SECRET=synthetic\n")

    def test_rejects_symlink_without_changing_target(self):
        target = Path(self.temp.name) / "target"
        target.write_text("SECRET=synthetic\n")
        target.chmod(0o600)
        Path(self.env["E2E_ENV_FILE"]).symlink_to(target)
        self.assertNotEqual(self.run_stack("config").returncode, 0)
        self.assertEqual(target.read_text(), "SECRET=synthetic\n")

    def test_down_is_scoped_and_preserves_volumes(self):
        binary = Path(self.temp.name) / "docker"
        binary.write_text('#!/bin/sh\ncase "$3:$4" in ps:*|volume:ls) exit 0;; esac\nprintf "%s\\n" "$@"\n')
        binary.chmod(0o700)
        result = self.run_stack("down", PATH=f"{self.temp.name}:{os.environ['PATH']}")
        self.assertEqual(result.returncode, 0, result.stderr)
        arguments = result.stdout.splitlines()
        self.assertEqual(
            arguments[:5],
            [
                "--context",
                "colima-factory",
                "compose",
                "--project-name",
                self.project,
            ],
        )
        self.assertEqual(arguments[-1], "down")
        self.assertNotIn("--volumes", arguments)
        self.assertNotIn("--remove-orphans", arguments)

    def test_check_rejects_missing_service_without_starting_it(self):
        namespace = runpy.run_path(str(STACK))
        check = namespace["check"]

        def fake_run(command, environment, **kwargs):
            self.assertEqual(command, ["compose", "ps", "--all", "--format", "json"])
            return subprocess.CompletedProcess(command, 0, stdout="")

        with patch.dict(
            check.__globals__,
            {
                "config": lambda *args: {"services": {"web": {}}},
                "run": fake_run,
            },
        ):
            with self.assertRaisesRegex(ValueError, "Service is not ready: web"):
                check(["compose"], {})

    def test_up_names_missing_press_settings_before_any_command(self):
        namespace = runpy.run_path(str(STACK))
        for missing in PRESS_ENVIRONMENT:
            with self.subTest(missing=missing):
                environment = {key: value for key, value in PRESS_ENVIRONMENT.items() if key != missing}
                with (
                    patch.dict(
                        namespace["up"].__globals__,
                        {
                            "resources": lambda *args: self.fail("Must reject before measuring"),
                            "run": lambda *args, **kwargs: self.fail("Must reject before Docker"),
                        },
                    ),
                    patch("subprocess.run", side_effect=AssertionError("Direct subprocess call")),
                ):
                    with self.assertRaisesRegex(ValueError, missing) as caught:
                        namespace["up"](["docker"], ["compose"], environment)
                for value in PRESS_ENVIRONMENT.values():
                    self.assertNotIn(value, str(caught.exception))

    def test_up_command_names_missing_press_settings_before_any_docker_call(self):
        namespace = runpy.run_path(str(STACK))
        for missing in (("ATONOTA_PRESS_SECRET",), ("ATONOTA_PRESS_URL", "ATONOTA_PRESS_SERVICE_SECRET")):
            with self.subTest(missing=missing):
                environment = {key: value for key, value in PRESS_ENVIRONMENT.items() if key not in missing}
                errors = io.StringIO()
                with (
                    patch("sys.argv", [str(STACK), "up"]),
                    patch.dict(
                        namespace["main"].__globals__,
                        {
                            "setup": lambda: (dict(environment), ["docker"], ["compose"]),
                            "run": lambda *args, **kwargs: self.fail("Must reject before Docker"),
                        },
                    ),
                    patch("subprocess.run", side_effect=AssertionError("Direct subprocess call")),
                    patch("subprocess.Popen", side_effect=AssertionError("Direct process start")),
                    contextlib.redirect_stderr(errors),
                ):
                    self.assertEqual(namespace["main"](), 2)
                message = errors.getvalue()
                for key in PRESS_ENVIRONMENT:
                    if key in missing:
                        self.assertIn(key, message)
                    else:
                        self.assertNotIn(key, message)
                for value in PRESS_ENVIRONMENT.values():
                    self.assertNotIn(value, message)

    def test_setup_supplies_every_press_setting_from_the_templates(self):
        namespace = runpy.run_path(str(STACK))
        with patch.dict(os.environ, self.env):
            environment, _, _ = namespace["setup"]()
        for key in PRESS_ENVIRONMENT:
            self.assertTrue(environment.get(key), key)

    def test_up_refuses_low_resources_before_building(self):
        namespace = runpy.run_path(str(STACK))
        up = namespace["up"]
        for measurements in ((9 * 1024 * 1024, 4096), (20 * 1024 * 1024, 2048)):
            with (
                self.subTest(measurements=measurements),
                patch.dict(
                    up.__globals__,
                    {
                        "resources": lambda *args: measurements,
                        "config": lambda *args: self.fail("Must reject before resolving or building"),
                    },
                ),
            ):
                with self.assertRaisesRegex(ValueError, "Startup requires"):
                    up([], [], dict(PRESS_ENVIRONMENT))

    def test_credentials_are_not_published_when_write_fails(self):
        namespace = runpy.run_path(str(STACK))
        path = Path(self.env["E2E_ENV_FILE"])
        with patch("os.fsync", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                namespace["credentials"](path)
        self.assertFalse(path.exists())
        self.assertEqual(list(path.parent.iterdir()), [])

    def test_owner_rejects_foreign_containers_before_mutation(self):
        namespace = runpy.run_path(str(STACK))
        outputs = [
            CONTAINER_ID,
            json.dumps(
                [
                    {
                        "Config": {
                            "Labels": {
                                "com.docker.compose.project.working_dir": "/another/worktree/backend/dev"
                            }
                        }
                    }
                ]
            ),
        ]
        with patch(
            "subprocess.run",
            side_effect=[subprocess.CompletedProcess([], 0, stdout=output) for output in outputs],
        ) as execute:
            with self.assertRaisesRegex(ValueError, "another worktree"):
                namespace["assert_owner"](
                    ["docker"], ["compose", "--env-file", self.env["E2E_ENV_FILE"]], {"PANE_PORT": "7150"}, create=True
                )
        self.assertEqual(execute.call_count, 2)

    def test_owner_rejects_foreign_saved_volumes(self):
        namespace = runpy.run_path(str(STACK))
        with patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=""),
                subprocess.CompletedProcess([], 0, stdout=self.project + "-owner\n"),
                subprocess.CompletedProcess(
                    [], 0, stdout=json.dumps([{"Labels": {"io.frappesetup.stack-owner": "different-owner"}}])
                ),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "saved volumes belong"):
                namespace["assert_owner"](
                    ["docker"], ["compose", "--env-file", self.env["E2E_ENV_FILE"]], {"PANE_PORT": "7150"}
                )

    def test_owner_rejects_unclaimed_volumes_before_creating_marker(self):
        namespace = runpy.run_path(str(STACK))
        with patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=""),
                subprocess.CompletedProcess([], 0, stdout=self.project + "_db\n"),
            ],
        ) as execute:
            with self.assertRaisesRegex(ValueError, "Unclaimed stack volumes"):
                namespace["assert_owner"](
                    ["docker"], ["compose", "--env-file", self.env["E2E_ENV_FILE"]], {"PANE_PORT": "7150"}, create=True
                )
        self.assertEqual(execute.call_count, 2)

    def test_build_explicitly_rebuilds_press_without_starting_services(self):
        namespace = runpy.run_path(str(STACK))
        calls = []

        def record(command, environment, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="")

        with (
            patch("sys.argv", [str(STACK), "build"]),
            patch.dict(
                namespace["main"].__globals__,
                {
                    "setup": lambda: ({}, ["docker"], ["compose"]),
                    "assert_owner": lambda *args, **kwargs: calls.append(
                        ["owner", kwargs.get("create", False)]
                    ),
                    "resources": lambda *args: (20 * 1024 * 1024, 4096),
                    "run": record,
                },
            ),
        ):
            self.assertEqual(namespace["main"](), 0)
        self.assertEqual(calls, [["owner", False], ["compose", "build", "web"]])

    def test_existing_press_site_migrates_after_source_copy(self):
        namespace = runpy.run_path(str(STACK))
        calls = []

        def record(command, environment, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=CONTAINER_ID)

        with (
            patch.dict(
                namespace["up"].__globals__,
                {
                    "resources": lambda *args: (20 * 1024 * 1024, 4096),
                    "config": lambda *args: {},
                    "ensure_images": lambda *args: None,
                    "check": lambda *args: None,
                    "run": record,
                },
            ),
            patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)),
        ):
            namespace["up"](["docker"], ["compose"], dict(PRESS_ENVIRONMENT))
        migrations = [
            command for command in calls if "bench --site press.localhost migrate" in " ".join(command)
        ]
        self.assertEqual(len(migrations), 1)
        copy_index = next(index for index, command in enumerate(calls) if command[1] == "cp")
        start_index = next(
            index for index, command in enumerate(calls) if "exec bench start" in " ".join(command)
        )
        self.assertLess(copy_index, calls.index(migrations[0]))
        self.assertLess(calls.index(migrations[0]), start_index)
        receiver_index = next(
            index
            for index, command in enumerate(calls)
            if command[-1] == "identity-sync" and command[1] == "up"
        )
        bootstrap_index = next(
            index for index, command in enumerate(calls) if "/workspace/dev/bootstrap.py" in command
        )
        self.assertLess(receiver_index, bootstrap_index)

    def test_resource_probe_uses_the_compose_redis_digest(self):
        namespace = runpy.run_path(str(STACK))
        manifest = (ROOT / "backend/dev/compose.tenant.yaml").read_text()
        expected = re.search(r"redis:7\.4-alpine@sha256:[a-f0-9]{64}", manifest).group()
        calls = []

        def record(command, environment, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(
                command, 0, stdout="Filesystem blocks used free\noverlay 30 10 20\nMem: 10 2 3 0 5 8\n"
            )

        with patch.dict(namespace["resources"].__globals__, {"run": record}):
            namespace["resources"](["docker"], {})
        self.assertIn(expected, calls[0])

    def test_migration_failure_stops_startup(self):
        namespace = runpy.run_path(str(STACK))
        calls = []

        def record(command, environment, **kwargs):
            calls.append(command)
            if "bench --site press.localhost migrate" in " ".join(command):
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout=CONTAINER_ID)

        with (
            patch.dict(
                namespace["up"].__globals__,
                {
                    "resources": lambda *args: (20 * 1024 * 1024, 4096),
                    "config": lambda *args: {},
                    "ensure_images": lambda *args: None,
                    "check": lambda *args: self.fail("Migration failure must stop readiness checks"),
                    "run": record,
                },
            ),
            patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                namespace["up"](["docker"], ["compose"], dict(PRESS_ENVIRONMENT))
        self.assertFalse(any("exec bench start" in " ".join(command) for command in calls))

    def test_rejects_environment_file_outside_the_repository(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        path = Path(outside.name) / ".env"
        result = self.run_stack("config", E2E_ENV_FILE=str(path))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("E2E_ENV_FILE", result.stderr)
        self.assertFalse(path.exists())

    def test_refuses_an_environment_file_that_git_could_track(self):
        candidates = (
            ROOT / "backend/e2e/stack-candidate.env",
            ROOT / "backend/e2e/tests/stack-candidate",
        )
        for path in candidates:
            with self.subTest(path=path):
                self.addCleanup(path.unlink, missing_ok=True)
                result = self.run_stack("config", E2E_ENV_FILE=str(path))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("ignored by Git", result.stderr)
                self.assertFalse(path.exists())

    def written_staging_paths(self, target):
        """Create credentials and return each staging file seen before publication."""
        namespace = runpy.run_path(str(STACK))
        seen = []
        real_link = os.link

        def link(source, destination):
            source = Path(source)
            self.assertTrue(source.is_file())
            self.assertEqual(source.parent, target.parent)
            namespace["assert_ignored"](source)
            seen.append(source)
            return real_link(source, destination)

        with patch("os.link", side_effect=link):
            namespace["credentials"](target)
        return seen

    def test_staging_name_does_not_depend_on_the_target_name(self):
        target = ROOT / "backend/e2e/.env.production"
        if target.exists() or target.is_symlink():
            self.skipTest("A developer file already uses this path.")
        self.addCleanup(target.unlink, missing_ok=True)
        for candidate in (target, Path(self.env["E2E_ENV_FILE"])):
            with self.subTest(target=candidate):
                seen = self.written_staging_paths(candidate)
                self.assertEqual(len(seen), 1)
                self.assertRegex(seen[0].name, r"\A\.fs-stack-env\.[0-9a-f]{16}\.tmp\Z")
                self.assertFalse(seen[0].exists())
                self.assertEqual(candidate.stat().st_mode & 0o777, 0o600)

    def test_first_run_creates_a_custom_ignored_target_and_removes_staging(self):
        target = ROOT / "backend/e2e/.env.production"
        if target.exists() or target.is_symlink():
            self.skipTest("A developer file already uses this path.")
        self.addCleanup(target.unlink, missing_ok=True)
        staging_before = set((ROOT / "backend/e2e").glob(".fs-stack-env.*"))
        result = self.run_stack("config", E2E_ENV_FILE=str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_file())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(set((ROOT / "backend/e2e").glob(".fs-stack-env.*")), staging_before)

    def test_refuses_a_staging_path_that_git_could_track(self):
        folder = ROOT / "backend/e2e" / ("staging-test-" + os.urandom(4).hex())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        folder.mkdir()
        target = folder / ".env"
        namespace = runpy.run_path(str(STACK))
        namespace["assert_ignored"](target)
        with self.assertRaisesRegex(ValueError, "ignored by Git"):
            namespace["credentials"](target)
        self.assertEqual(list(folder.iterdir()), [])

    def test_staging_ignore_rule_is_narrow(self):
        namespace = runpy.run_path(str(STACK))
        namespace["assert_ignored"](ROOT / "backend/e2e/.fs-stack-env.0123456789abcdef.tmp")
        for near in (
            "backend/e2e/.fs-stack-env.0123456789abcdef.tmp.md",
            "backend/e2e/.fs-stack-env.notes.tmp",
            "backend/e2e/docs/.fs-stack-env.0123456789abcdef.tmp",
            "src/.fs-stack-env.0123456789abcdef.tmp",
            "backend/e2e/.env.tmp-review.md",
            "src/.env.tmp-review",
        ):
            with self.subTest(path=near):
                with self.assertRaisesRegex(ValueError, "ignored by Git"):
                    namespace["assert_ignored"](ROOT / near)

    def test_git_ignore_check_cannot_be_redirected_by_git_variables(self):
        path = ROOT / "backend/e2e/stack-candidate.env"
        self.addCleanup(path.unlink, missing_ok=True)
        foreign = Path(self.temp.name) / "foreign"
        # Reuse the stack's validated runner so the test adds no new process call site.
        runpy.run_path(str(STACK))["run"]([shutil.which("git"), "init", "-q", str(foreign)], dict(os.environ))
        (foreign / ".gitignore").write_text("*\n")
        result = self.run_stack(
            "config",
            E2E_ENV_FILE=str(path),
            GIT_DIR=str(foreign / ".git"),
            GIT_WORK_TREE=str(ROOT),
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(path.exists())

    def test_rejects_environment_file_that_escapes_through_a_parent_symlink(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(outside.name, target_is_directory=True)
        result = self.run_stack("config", E2E_ENV_FILE=str(alias / ".env"))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(list(Path(outside.name).iterdir()), [])

    def test_rejects_environment_file_names_with_control_characters(self):
        for name in ("bad\nname.env", "bad\rname.env", "..", "."):
            with self.subTest(name=name):
                result = self.run_stack("config", E2E_ENV_FILE=str(Path(self.temp.name) / name))
                self.assertEqual(result.returncode, 2, result.stderr)
        # The OS refuses NUL in environment values, so check the validator directly.
        with self.assertRaisesRegex(ValueError, "control character"):
            runpy.run_path(str(STACK))["env_file"](str(Path(self.temp.name) / "bad\x00name.env"))

    def test_run_rejects_an_unvalidated_environment_file_before_execution(self):
        namespace = runpy.run_path(str(STACK))
        with patch("subprocess.run") as execute:
            for command in (
                ["docker", "compose", "--env-file", "/elsewhere/.env", "ps"],
                ["docker", "compose", "--env-file"],
                ["docker", "ps", "bad\x00argument"],
                ["docker", "ps", 7],
                [],
            ):
                with self.subTest(command=command):
                    with self.assertRaises(ValueError):
                        namespace["run"](command, {})
        execute.assert_not_called()

    def test_owner_rejects_malformed_container_ids_before_inspect(self):
        namespace = runpy.run_path(str(STACK))
        for output in ("--format={{json .}}", "0123456789ab;rm", "XYZ", "0123"):
            with self.subTest(output=output):
                with patch(
                    "subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=output)
                ) as execute:
                    with self.assertRaisesRegex(ValueError, "container ID"):
                        namespace["assert_owner"](
                            ["docker"],
                            ["compose", "--env-file", self.env["E2E_ENV_FILE"]],
                            {"PANE_PORT": "7150"},
                        )
                self.assertEqual(execute.call_count, 1)

    def test_up_rejects_malformed_container_ids_before_stats(self):
        namespace = runpy.run_path(str(STACK))
        calls = []

        def record(command, environment, **kwargs):
            calls.append(command)
            stdout = "--no-trunc\n" if command[-2:] == ["ps", "-q"] else CONTAINER_ID
            return subprocess.CompletedProcess(command, 0, stdout=stdout)

        with patch.dict(
            namespace["up"].__globals__,
            {
                "resources": lambda *args: (20 * 1024 * 1024, 4096),
                "config": lambda *args: {},
                "ensure_images": lambda *args: None,
                "check": lambda *args: None,
                "run": record,
            },
        ):
            with self.assertRaisesRegex(ValueError, "container ID"):
                namespace["up"](["docker"], ["compose"], dict(PRESS_ENVIRONMENT))
        self.assertFalse(any("stats" in command for command in calls))

    def test_ready_probe_uses_the_validating_runner(self):
        namespace = runpy.run_path(str(STACK))
        calls = []

        def record(command, environment, check=True, **kwargs):
            calls.append((command, check))
            return subprocess.CompletedProcess(command, 0, stdout=CONTAINER_ID)

        with (
            patch.dict(
                namespace["up"].__globals__,
                {
                    "resources": lambda *args: (20 * 1024 * 1024, 4096),
                    "config": lambda *args: {},
                    "ensure_images": lambda *args: None,
                    "check": lambda *args: None,
                    "run": record,
                },
            ),
            patch("subprocess.run", side_effect=AssertionError("Direct subprocess call")),
        ):
            namespace["up"](["docker"], ["compose"], dict(PRESS_ENVIRONMENT))
        probe = ["compose", "exec", "-T", "web", "test", "-f", "/home/frappe/benches/.stack-installed"]
        self.assertIn((probe, False), calls)

    def owner_with_container(self, label_path, port="7150", volumes=""):
        namespace = runpy.run_path(str(STACK))
        containers = [
            {
                "Config": {
                    "Labels": {
                        "com.docker.compose.project.working_dir": str(ROOT / "backend/dev"),
                        "com.docker.compose.project.environment_file": str(label_path),
                    },
                    "Env": [f"KC_HTTP_PORT={port}"],
                }
            }
        ]
        with patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=CONTAINER_ID),
                subprocess.CompletedProcess([], 0, stdout=json.dumps(containers)),
                subprocess.CompletedProcess([], 0, stdout=volumes),
            ],
        ):
            namespace["assert_owner"](
                ["docker"],
                ["compose", "--env-file", self.env["E2E_ENV_FILE"]],
                {"PANE_PORT": "7150", "KC_PORT": "7150"},
            )

    def test_owner_accepts_environment_path_through_parent_symlink(self):
        parent = Path(self.temp.name)
        actual = parent / "actual"
        actual.mkdir()
        alias = parent / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        self.env["E2E_ENV_FILE"] = str(actual / ".env")
        self.owner_with_container(alias / ".env")

    def test_owner_rejects_other_environment_file(self):
        with self.assertRaisesRegex(ValueError, "another environment file"):
            self.owner_with_container(Path(self.temp.name) / "another.env")

    def test_owner_rejects_other_port_range(self):
        with self.assertRaisesRegex(ValueError, "another Pane port range"):
            self.owner_with_container(self.env["E2E_ENV_FILE"], port="7160")

    def test_matching_container_cannot_claim_unowned_volumes(self):
        with self.assertRaisesRegex(ValueError, "Unclaimed stack volumes"):
            self.owner_with_container(self.env["E2E_ENV_FILE"], volumes=self.project + "_db\n")

    def test_legacy_env_without_mcp_urls_uses_local_defaults_without_rewriting_env_file(self):
        namespace = runpy.run_path(str(STACK))
        path = Path(self.env["E2E_ENV_FILE"])
        namespace["credentials"](path)
        kept = [
            line
            for line in path.read_text().splitlines()
            if not line.startswith(("ATONOTA_MCP_REDIRECT_URI=", "ATONOTA_MCP_RESOURCE_URL="))
        ]
        path.write_text("\n".join(kept) + "\n")
        before = path.read_bytes()

        result = self.run_stack("config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)

        with patch.dict(os.environ, self.env):
            environment, _, compose = namespace["setup"]()
        model = namespace["config"](compose, environment)
        keycloak_env = model["services"]["keycloak"]["environment"]
        self.assertEqual(
            keycloak_env["ATONOTA_MCP_REDIRECT_URI"],
            "https://mcp-client.example.test/callback",
        )
        self.assertEqual(
            keycloak_env["ATONOTA_MCP_RESOURCE_URL"],
            "https://tenant.example.test/api/method/platform_core.api.ai.mcp",
        )
        self.assertEqual(path.read_bytes(), before)

    def test_legacy_env_missing_mcp_secret_names_missing_key_before_docker(self):
        namespace = runpy.run_path(str(STACK))
        path = Path(self.env["E2E_ENV_FILE"])
        namespace["credentials"](path)
        kept = [
            line
            for line in path.read_text().splitlines()
            if not line.startswith(
                (
                    "ATONOTA_MCP_REDIRECT_URI=",
                    "ATONOTA_MCP_RESOURCE_URL=",
                    "ATONOTA_MCP_INTROSPECTION_SECRET=",
                )
            )
        ]
        path.write_text("\n".join(kept) + "\n")
        before = path.read_bytes()
        docker = Path(self.temp.name) / "docker"
        docker.write_text("#!/bin/sh\nexit 99\n")
        docker.chmod(0o700)
        for key in list(self.env):
            if key.startswith("ATONOTA_MCP_"):
                self.env.pop(key)

        for action in ("config", "up"):
            with self.subTest(action=action):
                result = self.run_stack(action, PATH=f"{self.temp.name}:{os.environ['PATH']}")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("ATONOTA_MCP_INTROSPECTION_SECRET", result.stderr)
                self.assertNotIn("ATONOTA_MCP_REDIRECT_URI", result.stderr)
                self.assertNotIn("ATONOTA_MCP_RESOURCE_URL", result.stderr)
                self.assertEqual(path.read_bytes(), before)
                for line in before.decode().splitlines():
                    key, value = line.split("=", 1)
                    if value and ("SECRET" in key or "PASSWORD" in key):
                        self.assertNotIn(value, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
