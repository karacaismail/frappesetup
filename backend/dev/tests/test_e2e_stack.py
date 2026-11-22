"""The shared stack must isolate services and never expose credentials."""

import json
import os
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "backend/e2e/stack"


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

    def run_stack(self, action, **environment):
        return subprocess.run(
            ["python3.14", str(STACK), action],
            env=dict(self.env, **environment),
            capture_output=True,
            text=True,
        )

    def test_config_combines_services_and_loopback_ports(self):
        result = self.run_stack("config")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["name"], "fs-e2e-ortam")
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
                "mailpit",
                "web",
                "mariadb",
                "redis",
            },
        )
        ports = {
            port["published"] for service in config["services"].values() for port in service.get("ports", [])
        }
        self.assertEqual(ports, {str(7150 + offset) for offset in (0, 1, 2, 3, 4, 6)})
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
                "fs-e2e-ortam",
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
                    up([], [], {})

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
            "container-id",
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
                    ["docker"], ["compose", "--env-file", "/unused/.env"], {"PANE_PORT": "7150"}, create=True
                )
        self.assertEqual(execute.call_count, 2)

    def test_owner_rejects_foreign_saved_volumes(self):
        namespace = runpy.run_path(str(STACK))
        with patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=""),
                subprocess.CompletedProcess([], 0, stdout="fs-e2e-ortam-owner\n"),
                subprocess.CompletedProcess(
                    [], 0, stdout=json.dumps([{"Labels": {"io.frappesetup.stack-owner": "different-owner"}}])
                ),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "saved volumes belong"):
                namespace["assert_owner"](
                    ["docker"], ["compose", "--env-file", "/unused/.env"], {"PANE_PORT": "7150"}
                )

    def test_owner_rejects_unclaimed_volumes_before_creating_marker(self):
        namespace = runpy.run_path(str(STACK))
        with patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=""),
                subprocess.CompletedProcess([], 0, stdout="fs-e2e-ortam_db\n"),
            ],
        ) as execute:
            with self.assertRaisesRegex(ValueError, "Unclaimed stack volumes"):
                namespace["assert_owner"](
                    ["docker"], ["compose", "--env-file", "/unused/.env"], {"PANE_PORT": "7150"}, create=True
                )
        self.assertEqual(execute.call_count, 2)


if __name__ == "__main__":
    unittest.main()
