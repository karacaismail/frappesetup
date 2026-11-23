"""osv-setup --if-stale: the Jenkins line refreshes the OSV database only when it is old.

Review 2, finding 2. Scheduled jobs are not allowed, so backend.Jenkinsfile runs
"osv-setup --if-stale" before the gates. A database file that is missing or at least six days
old is downloaded again; a newer one is kept. The scan itself accepts at most seven days.

The test uses a fake curl and a copy of the pinned scanner that osv-setup downloaded before. It is
skipped where that copy is missing, because the script checks the scanner's SHA-256.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SETUP = BACKEND / "dev" / "security" / "osv-setup"
CACHED = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "frappesetup-osv" / "bin" / "osv-scanner"

FAKE_CURL = r"""#!/usr/bin/env bash
out=""
while [ $# -gt 0 ]; do
    case "$1" in
    -fsSLo) out="$2"; shift 2 ;;
    *) url="$1"; shift ;;
    esac
done
printf '%s\n' "$url" >>"$CURL_LOG"
printf 'fake database\n' >"$out"
"""

DAY = 24 * 60 * 60
BASH = shutil.which("bash") or "/bin/bash"


def pinned_sum():
    """The scanner checksum for this machine, as written in tool-versions.env."""
    machine = {"Darwin-arm64": "DARWIN_ARM64", "Linux-x86_64": "LINUX_AMD64",
               "Linux-aarch64": "LINUX_ARM64"}.get(f"{platform.system()}-{platform.machine()}")
    versions = dict(line.split("=", 1) for line in
                    (BACKEND / "dev" / "security" / "tool-versions.env").read_text().splitlines())
    return versions.get(f"OSV_SHA256_{machine}") if machine else None


class OsvSetupPins(unittest.TestCase):
    def test_checksums_live_in_tool_versions(self):
        # Small finding 1: scans.py checks a scanner on PATH against the same checksums.
        versions = (BACKEND / "dev" / "security" / "tool-versions.env").read_text()
        for name in ("DARWIN_ARM64", "LINUX_AMD64", "LINUX_ARM64"):
            with self.subTest(platform=name):
                self.assertRegex(versions, rf"(?m)^OSV_SHA256_{name}=[0-9a-f]{{64}}$")
                self.assertIn(f"$OSV_SHA256_{name}", SETUP.read_text())
        self.assertNotRegex(SETUP.read_text(), r"sum=[0-9a-f]{64}")


@unittest.skipUnless(CACHED.is_file() and pinned_sum()
                     and hashlib.sha256(CACHED.read_bytes()).hexdigest() == pinned_sum(),
                     "the pinned OSV-Scanner from osv-setup is not cached on this machine")
class OsvSetupRefresh(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="osv-setup-test-"))
        self.addCleanup(shutil.rmtree, self.temp)
        tools = self.temp / "tools"
        tools.mkdir()
        (tools / "curl").write_text(FAKE_CURL)
        (tools / "curl").chmod(0o755)
        cache = self.temp / "cache" / "frappesetup-osv"
        (cache / "bin").mkdir(parents=True)
        shutil.copy2(CACHED, cache / "bin" / "osv-scanner")
        self.db = cache / "db" / "osv-scalibr"
        self.log = self.temp / "curl.log"
        self.env = {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
                    "XDG_CACHE_HOME": str(self.temp / "cache"), "CURL_LOG": str(self.log)}
        self.env.pop("OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY", None)

    def database(self, ecosystem, age):
        path = self.db / ecosystem / "all.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old database\n")
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return path

    def run_setup(self, *args):
        process = subprocess.run([BASH, str(SETUP), *args], env=self.env, capture_output=True, text=True)
        downloads = self.log.read_text().split() if self.log.exists() else []
        return process, downloads

    def test_fresh_databases_are_kept(self):
        self.database("PyPI", 60 * 60)
        self.database("npm", 5 * DAY)
        process, downloads = self.run_setup("--if-stale")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(downloads, [])

    def test_old_or_missing_databases_are_downloaded(self):
        old = self.database("PyPI", 8 * DAY)
        process, downloads = self.run_setup("--if-stale")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(sorted(url.rsplit("/", 2)[1] for url in downloads), ["PyPI", "npm"])
        self.assertEqual(old.read_text(), "fake database\n")
        self.assertGreater(old.stat().st_mtime, time.time() - DAY)

    def test_without_the_option_every_database_is_downloaded(self):
        self.database("PyPI", 60 * 60)
        self.database("npm", 60 * 60)
        process, downloads = self.run_setup()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(len(downloads), 2)

    def test_unknown_option_is_refused(self):
        process, downloads = self.run_setup("--weekly")
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(downloads, [])


if __name__ == "__main__":
    unittest.main()
