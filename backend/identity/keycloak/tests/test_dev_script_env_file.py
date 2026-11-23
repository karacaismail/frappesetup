"""Review 1, finding 1 and minor finding 3: how `bin/kc-dev.sh` reads the `.env` file.

The script reads the file line by line, the way `docker run --env-file` does. The rest of the line is
the value, with no shell quoting. So a value with a space, like "AtonotA Login", stays whole. If the
file were run by the shell again, these tests would fail.

The tests run a copy of the real script. A stand-in `docker` command records the environment it
receives. No live stack, container or real secret is used.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import DIRECTORY

SCRIPT = DIRECTORY / "bin" / "kc-dev.sh"

# A full path to bash keeps the call free of a PATH lookup (Bandit B607).
# Without bash the test cannot run the script, so it stops with a clear error instead of skipping.
BASH = shutil.which("bash")

# The stand-in docker writes the environment it receives to a JSON file and exits.
STAND_IN = f"""#!{sys.executable}
import json, os
with open(os.environ["ENV_DUMP"], "w", encoding="utf-8") as file:
    json.dump(dict(os.environ), file)
"""


class EnvFileReadingTest(unittest.TestCase):
    def setUp(self):
        if not BASH:
            self.fail("bash was not found on PATH; these tests need bash to run bin/kc-dev.sh.")
        self.dir = Path(tempfile.mkdtemp(prefix="kc-dev-env-"))
        root = self.dir / "backend" / "identity" / "keycloak"
        (root / "bin").mkdir(parents=True)
        shutil.copy2(SCRIPT, root / "bin" / "kc-dev.sh")
        self.script = root / "bin" / "kc-dev.sh"
        bin_dir = self.dir / "stand-ins"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text(STAND_IN, encoding="utf-8")
        docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
        self.dump = self.dir / "env.json"
        self.env_file = self.dir / "test.env"
        # The script adds missing keys from .env.example. An empty example keeps the test file as written.
        (root / ".env.example").write_text("", encoding="utf-8")
        self.env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(self.dir),
            "PANE_PORT": "5990",
            "KC_ENV_FILE": str(self.env_file),
            "ENV_DUMP": str(self.dump),
            "COMPOSE_PROJECT_NAME": "fs-kimlik-realm-env-test",
        }

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_script(self, content: bytes) -> subprocess.CompletedProcess:
        self.env_file.write_bytes(content)
        return subprocess.run(
            [BASH, str(self.script), "config", "--quiet"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def exported(self) -> dict:
        return json.loads(self.dump.read_text(encoding="utf-8"))

    def test_values_are_read_without_the_shell(self):
        result = self.run_script(
            b"# A comment line\n"
            b"\n"
            b"IDENTITY_BRAND_NAME=AtonotA Login\n"
            b"TEST_VALUE_WITH_EQUALS=a=b==c\n"
            b"   \n"
            b"  # An indented comment\n"
            b"TEST_EMPTY_VALUE=\n"
            b"TEST_LAST_LINE=no newline at the end"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.exported()
        self.assertEqual(values["IDENTITY_BRAND_NAME"], "AtonotA Login")
        self.assertEqual(values["TEST_VALUE_WITH_EQUALS"], "a=b==c")
        self.assertEqual(values["TEST_EMPTY_VALUE"], "")
        self.assertEqual(values["TEST_LAST_LINE"], "no newline at the end")
        self.assertEqual(values["KC_PORT"], "5990")

    def test_crlf_line_endings_are_removed(self):
        result = self.run_script(
            b"# A comment written on Windows\r\n"
            b"\r\n"
            b"IDENTITY_BRAND_NAME=AtonotA Login\r\n"
            b"TEST_VALUE_WITH_EQUALS=a=b\r\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.exported()
        self.assertEqual(values["IDENTITY_BRAND_NAME"], "AtonotA Login")
        self.assertEqual(values["TEST_VALUE_WITH_EQUALS"], "a=b")

    def test_quotes_and_trailing_comments_stay_in_the_value(self):
        # Decision: the value is taken as written, the same as "docker run --env-file".
        # prod-check passes the same file to docker that way, so both paths see the same value.
        result = self.run_script(b"TEST_QUOTED=\"AtonotA Login\"\nTEST_COMMENT=1 # note\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.exported()
        self.assertEqual(values["TEST_QUOTED"], '"AtonotA Login"')
        self.assertEqual(values["TEST_COMMENT"], "1 # note")

    def assert_rejected(self, content: bytes, line_number: int):
        result = self.run_script(content)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(f"{self.env_file}:{line_number}", result.stderr)
        self.assertIn("expected KEY=value, without \"export\"", result.stderr)
        self.assertFalse(self.dump.exists(), "docker must not run after a bad line")

    def test_export_line_gives_a_clear_error(self):
        self.assert_rejected(b"# comment\nTEST_OK=1\nexport TEST_BAD=1\n", 3)

    def test_line_without_equals_gives_a_clear_error(self):
        self.assert_rejected(b"TEST_OK=1\nthis is not a setting\n", 2)

    def test_bad_key_gives_a_clear_error(self):
        self.assert_rejected(b"1TEST=1\n", 1)
        self.assert_rejected(b"TEST KEY=1\n", 1)

    def test_bad_line_never_runs_a_command(self):
        marker = self.dir / "pwned"
        self.assert_rejected(f"a[$(touch {marker})]=1\n".encode(), 1)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
