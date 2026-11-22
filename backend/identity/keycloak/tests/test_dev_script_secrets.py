"""Merge review O5: `bin/kc-dev.sh prod-check` must not put a secret value on a command line.

Anyone who can read the local process list could read it there. The test runs the real script with
stand-in `docker`, `curl` and `ssh` commands that only record their arguments. It uses its own
environment file with a made-up secret, so no development secret is touched.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import DIRECTORY

SCRIPT = DIRECTORY / "bin" / "kc-dev.sh"
FAKE_SECRET = "fake-webhook-secret-for-the-argv-test-7f3a"  # gitleaks:allow (synthetic test value)

STAND_IN = """#!/bin/sh
printf '%s\\n' "${0##*/} $*" >> "$ARGV_LOG"
if [ -n "$KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET" ] && [ "${0##*/}" = docker ]; then
  case "$*" in *" run "*) [ "$KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET" = "$EXPECTED_SECRET" ] \\
    && echo "secret-in-env" >> "$ARGV_LOG" ;; esac
fi
if [ "${0##*/}" = curl ]; then
  case "$*" in
    */realms/platform)
      case "${UNREADY_KEYCLOAK:-}" in
        yes) exit 22 ;;
        redirect) printf '%s\\n' 302; exit 0 ;;
        *) printf '%s\\n' 200; exit 0 ;;
      esac ;;
  esac
fi
if [ "${0##*/}" = seq ]; then
  printf '%s\\n' 1 2
  exit 0
fi
case " $* " in
  *" config "*--quiet*) ;;
  *" config "*)
    case "$*" in *--no-interpolate*--no-env-resolution*) ;; *) printf '%s\\n' "$IDENTITY_SYNC_WEBHOOK_SECRET" ;; esac ;;
  *inspect*) echo false ;;
  *" logs "*) echo "webhook URL must use https" ;;
esac
exit 0
"""


class ProdCheckSecretTest(unittest.TestCase):
    """Runs a copy of the script in its own folder, so no real tunnel file, port or Python run is touched."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="kc-dev-argv-"))
        root = self.dir / "backend" / "identity" / "keycloak"
        (root / "bin").mkdir(parents=True)
        (root / "tests").mkdir()
        shutil.copy2(SCRIPT, root / "bin" / "kc-dev.sh")
        shutil.copy2(DIRECTORY / ".env.example", root / ".env.example")
        self.script = root / "bin" / "kc-dev.sh"
        self.root = root
        bin_dir = self.dir / "stand-ins"
        bin_dir.mkdir()
        for name in ("docker", "curl", "ssh", "python3", "sleep", "seq"):
            path = bin_dir / name
            path.write_text(STAND_IN, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        self.log = self.dir / "argv.log"
        env_file = self.dir / "test.env"
        lines = []
        for line in (DIRECTORY / ".env.example").read_text(encoding="utf-8").splitlines():
            if line.startswith("IDENTITY_SYNC_WEBHOOK_SECRET="):
                line = f"IDENTITY_SYNC_WEBHOOK_SECRET={FAKE_SECRET}"
            elif "=degistir-" in line:
                line = line.split("=", 1)[0] + "=fake-value-for-the-argv-test"
            lines.append(line)
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(self.dir),
            "PANE_PORT": "5990",
            "KC_ENV_FILE": str(env_file),
            "ARGV_LOG": str(self.log),
            "EXPECTED_SECRET": FAKE_SECRET,
            "COMPOSE_PROJECT_NAME": "fs-kimlik-realm-argv-test",
        }

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_config_preview_never_resolves_secrets(self):
        result = subprocess.run(
            ["bash", str(self.script), "config"], env=self.env, capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(FAKE_SECRET in result.stdout)
        self.assertIn("config --no-interpolate --no-env-resolution", self.log.read_text(encoding="utf-8"))

    def test_config_refuses_environment_output(self):
        result = subprocess.run(
            ["bash", str(self.script), "config", "--environment"], env=self.env, capture_output=True,
            text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(FAKE_SECRET in result.stdout)
        self.assertFalse(self.log.exists())

    def test_prod_check_stops_if_the_server_never_becomes_ready(self):
        result = subprocess.run(
            ["bash", str(self.script), "prod-check"], env={**self.env, "UNREADY_KEYCLOAK": "yes"},
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Production Keycloak did not become ready.", result.stderr)
        recorded = self.log.read_text(encoding="utf-8")
        self.assertNotIn("python3 -I -m unittest", recorded)
        probes = [line for line in recorded.splitlines()
                  if line.startswith("curl ") and line.endswith("/realms/platform")]
        self.assertEqual(len(probes), 2)
        self.assertTrue(all("--max-time 2" in line for line in probes))

    def test_redirect_does_not_mean_keycloak_is_ready(self):
        result = subprocess.run(
            ["bash", str(self.script), "prod-check"], env={**self.env, "UNREADY_KEYCLOAK": "redirect"},
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("python3 -I -m unittest", self.log.read_text(encoding="utf-8"))

    def test_prod_check_keeps_the_secret_off_every_command_line(self):
        subprocess.run(["bash", str(self.script), "prod-check"], env=self.env, capture_output=True,
                       timeout=600, check=False)
        recorded = self.log.read_text(encoding="utf-8")
        runs = [line for line in recorded.splitlines() if line.startswith("docker ") and " run " in line]
        self.assertEqual(len(runs), 2, "both prod containers must be started")
        for run in runs:
            self.assertIn(f"--env-file {self.env['KC_ENV_FILE']}", run, "the test's own env file must be used")
            self.assertIn("-e KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET ", run, "pass the secret by name only")
        self.assertNotIn(FAKE_SECRET, recorded, "a secret value reached a command line")
        self.assertEqual(recorded.count("secret-in-env"), 2, "docker must get the secret from the environment")
        self.assertIn("python3 -I -m unittest", recorded, "the final test run must be the stand-in")

if __name__ == "__main__":
    unittest.main()
