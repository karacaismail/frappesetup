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


if __name__ == "__main__":
    unittest.main()
