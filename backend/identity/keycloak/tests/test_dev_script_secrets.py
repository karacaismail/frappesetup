"""Merge review O5: `bin/kc-dev.sh prod-check` must not put a secret value on a command line.

Anyone who can read the local process list could read it there. The test runs the real script with
stand-in `docker`, `curl` and `ssh` commands that only record their arguments. It uses its own
environment file with a made-up secret, so no development secret is touched.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from yardimci import KLASOR

SCRIPT = KLASOR / "bin" / "kc-dev.sh"
FAKE_SECRET = "fake-webhook-secret-for-the-argv-test-7f3a"  # gitleaks:allow (synthetic test value)

STAND_IN = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$ARGV_LOG"
case "$*" in
  *inspect*) echo false ;;
  *" logs "*) echo "webhook URL must use https" ;;
esac
exit 0
"""


class ProdCheckSecretTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="kc-dev-argv-"))
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        for name in ("docker", "curl", "ssh"):
            path = bin_dir / name
            path.write_text(STAND_IN, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        self.log = self.dir / "argv.log"
        env_file = self.dir / "test.env"
        lines = []
        for line in (KLASOR / ".env.example").read_text(encoding="utf-8").splitlines():
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
            "COMPOSE_PROJECT_NAME": "fs-kimlik-realm-argv-test",
        }

    def tearDown(self):
        for path in sorted(self.dir.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.dir.rmdir()

    def test_prod_check_keeps_the_secret_off_every_command_line(self):
        subprocess.run(["bash", str(SCRIPT), "prod-check"], env=self.env, capture_output=True,
                       timeout=600, check=False)
        recorded = self.log.read_text(encoding="utf-8")
        self.assertIn(" run ", recorded, "the stand-in docker must have been called")
        self.assertNotIn(FAKE_SECRET, recorded, "a secret value reached a command line")
        self.assertIn(f"--env-file {self.env['KC_ENV_FILE']}", recorded, "the test's own env file must be used")


if __name__ == "__main__":
    unittest.main()
