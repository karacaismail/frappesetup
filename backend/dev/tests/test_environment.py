"""Safety contracts for local environment scripts."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

DEV = Path(__file__).resolve().parents[1]


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get("PANE_SCRATCH_DIR", DEV.parents[1] / ".pane/scratch"))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.env_path = Path(self.temp.name) / ".env"
        self.env = dict(os.environ, DEV_ENV_FILE=str(self.env_path))

    def init(self):
        return subprocess.run(
            ["python3", str(DEV / "init_env.py")], env=self.env, capture_output=True, text=True
        )

    def test_private_credentials_are_created_once_and_never_printed(self):
        self.assertEqual(self.init().returncode, 0)
        original = self.env_path.read_bytes()
        self.assertEqual(stat.S_IMODE(self.env_path.stat().st_mode), 0o600)
        result = self.init()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.env_path.read_bytes(), original)
        for line in original.decode().splitlines():
            value = line.split("=", 1)[1]
            self.assertGreaterEqual(len(value), 32)
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_existing_public_env_is_rejected_without_modification(self):
        self.env_path.write_text("TEST=synthetic")
        self.env_path.chmod(0o644)
        self.assertNotEqual(self.init().returncode, 0)
        self.assertEqual(self.env_path.read_text(), "TEST=synthetic")

    def test_symlink_is_rejected(self):
        target = self.env_path.with_name("target")
        target.write_text("synthetic")
        self.env_path.symlink_to(target)
        self.assertNotEqual(self.init().returncode, 0)
        self.assertEqual(target.read_text(), "synthetic")

    def test_bad_ports_fail_before_docker(self):
        for port in ["", "0010", "65527", "not-a-port"]:
            with self.subTest(port=port):
                result = subprocess.run(
                    [str(DEV / "bin/compose"), "config", "--quiet"],
                    env=dict(self.env, PANE_PORT=port),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)

    def test_bad_app_names_fail_before_starting_services(self):
        for app in ["../frappe", "--help", "app;exit", "bad-app"]:
            with self.subTest(app=app):
                result = subprocess.run(
                    [str(DEV / "bin/test"), app], env=self.env, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 2)
        self.assertFalse(self.env_path.exists())

    def run_test_command(self, app, allow_tests_status):
        """Run bin/test with a fake Compose. The allow_tests check exits with the given status."""
        dev = Path(self.temp.name) / "dev"
        (dev / "bin").mkdir(parents=True, exist_ok=True)
        (dev / "bin/test").write_bytes((DEV / "bin/test").read_bytes())
        (dev / "init_env.py").write_text("")
        log = Path(self.temp.name) / "compose.log"
        log.write_text("")
        compose = dev / "bin/compose"
        compose.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' \"$*\" >> '{log}'\n"
            f'if [[ "$*" == *allow_tests* ]]; then exit {allow_tests_status}; fi\n'
        )
        for script in (dev / "bin/test", compose):
            script.chmod(0o755)
        result = subprocess.run([str(dev / "bin/test"), app], env=self.env, capture_output=True, text=True)
        return result, log.read_text()

    def test_test_command_fails_when_the_site_disables_tests(self):
        """Frappe's run-tests prints "Testing is disabled" and exits 0 (MVP test 3, T-18)."""
        result, log = self.run_test_command("platform_core", 3)
        self.assertEqual(result.returncode, 3)
        self.assertIn("allow_tests", result.stderr)
        self.assertNotIn("run-tests", log)

    def test_test_command_passes_other_check_failures_through(self):
        result, log = self.run_test_command("platform_core", 1)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("allow_tests is not true", result.stderr)
        self.assertNotIn("run-tests", log)

    def test_test_command_runs_the_tests_when_the_site_allows_them(self):
        for app in ("platform_core", "hrms_tr"):
            with self.subTest(app=app):
                result, log = self.run_test_command(app, 0)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"bench --site test-{app.replace('_', '-')}.localhost run-tests --app {app}", log)

if __name__ == "__main__":
    unittest.main()
