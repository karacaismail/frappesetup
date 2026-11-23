"""Tests for the server side scripts in deploy/remote with a fake docker command.

The fake docker writes every call to a log and runs nothing. The tests check the order of the
release steps, the links and the rollback. They need GNU tools (mv -T, sha256sum), so they run on
Linux, as the Jenkins agents and the servers do. On other systems they are skipped.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import release  # noqa: E402

FAKE_DOCKER = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_LOG"
# Read what a pipe sends, as the real command would; otherwise the writer gets SIGPIPE.
cat >/dev/null
if [[ -n "${FAKE_FAIL:-}" && "$*" == *"$FAKE_FAIL"* ]]; then
    exit 1
fi
case "$*" in
*" ps --format"*) printf 'tenant-web running healthy\nkeycloak running healthy\n' ;;
*"tar -C"*"-cf -"*) tar -cf - -T /dev/null ;;
*"pg_dump"*) printf 'dump\n' ;;
*"cat /tmp/backup.sqlite3"*) printf 'sqlite\n' ;;
esac
exit 0
"""


def gnu_tools():
    probe = subprocess.run(["mv", "--version"], capture_output=True, text=True)
    return probe.returncode == 0 and "GNU" in probe.stdout


def commit(number):
    return f"{number:040x}"


@unittest.skipUnless(gnu_tools(), "needs GNU coreutils (Linux)")
class RemoteScripts(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        self.root = self.folder / "srv"
        self.etc = self.folder / "etc"
        self.log = self.folder / "docker.log"
        fake_bin = self.folder / "bin"
        fake_bin.mkdir()
        (fake_bin / "docker").write_text(FAKE_DOCKER)
        (fake_bin / "docker").chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
            "ATONOTA_ROOT": str(self.root),
            "ATONOTA_ETC": str(self.etc),
        }

    def incoming(self, env, manifest, bundle=None):
        folder = self.folder / f"incoming-{env}-{manifest['release_id']}"
        folder.mkdir()
        (folder / "release.json").write_text(json.dumps(manifest))
        shutil.copy(DEPLOY / "environments" / f"{env}.env", folder)
        for name in ("stack.yaml", "edge.yaml", "Caddyfile", "site.caddy.template"):
            shutil.copy(DEPLOY / "compose" / name, folder)
        for script in (DEPLOY / "remote").iterdir():
            shutil.copy(script, folder)
        if bundle:
            name, data = bundle
            (folder / name).write_bytes(data)
        return folder

    def apply(self, env, manifest, bundle=None, **extra):
        folder = self.incoming(env, manifest, bundle)
        return subprocess.run(
            [str(folder / "apply"), env, str(folder)],
            env={**self.environment, **extra},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )

    def run_remote(self, env, script, *arguments, **extra):
        return subprocess.run(
            [str(self.root / env / "bin" / script), env, *arguments],
            env={**self.environment, **extra},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )

    def backend(self, number, env="alpha"):
        components = {
            name: {"image": f"ghcr.io/karacaismail/atonota-{name}@sha256:{number:064x}"}
            for name in ("tenant", "keycloak", "identity-sync")
        }
        if env in ("rc", "prod"):
            components["press"] = {"image": f"ghcr.io/karacaismail/atonota-press@sha256:{number:064x}"}
        return release.new_manifest("backend", commit(number), number, components)

    def web(self, number):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            html = f'<script type="module" src="/panel/assets/index-{number}.js"></script>'.encode()
            for name, data in (("index.html", html), (f"assets/index-{number}.js", b"1")):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        data = buffer.getvalue()
        name = f"atonota-web-{commit(number)[:12]}.tar.gz"
        manifest = release.new_manifest(
            "web", commit(number), number, {"panel": {"file": name, "sha256": hashlib.sha256(data).hexdigest()}}
        )
        return manifest, (name, data)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def index(self, fragment, start=0):
        for number, line in enumerate(self.calls()[start:], start):
            if fragment in line:
                return number
        self.fail(f"no docker call with {fragment!r}")

    def link(self, env, name):
        return os.readlink(self.root / env / name)

    def first_install(self, env="alpha"):
        result = self.apply(env, self.backend(1, env), ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.log.unlink()

    def test_first_release_needs_the_first_install_flag(self):
        result = self.apply("alpha", self.backend(1))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("first install", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_first_install_migrates_then_starts(self):
        result = self.apply("alpha", self.backend(1), ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        pull = self.index(" pull --quiet")
        migrate = self.index("bench --site demo.app.alpha.atonota.net migrate")
        start = self.index("--remove-orphans")
        reload = self.index("caddy reload")
        self.assertLess(pull, migrate)
        self.assertLess(migrate, start)
        self.assertLess(start, reload)
        self.assertFalse(any("backup" in line for line in self.calls()))
        self.assertEqual(self.link("alpha", "backend-current"), f"releases/backend-{commit(1)[:12]}-b1")
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())
        site = (self.root / "edge" / "sites" / "alpha.caddy").read_text()
        self.assertIn("id.alpha.atonota.net {", site)
        self.assertIn("demo.app.alpha.atonota.net {", site)
        self.assertIn("reverse_proxy alpha-keycloak:8080", site)
        self.assertNotIn("__", site)

    def test_next_release_backs_up_before_it_stops_and_migrates(self):
        self.first_install()
        result = self.apply("alpha", self.backend(2))
        self.assertEqual(result.returncode, 0, result.stderr)
        pull = self.index(" pull --quiet")
        backup = self.index("backup --with-files")
        dump = self.index("pg_dump")
        maintenance = self.index("set-maintenance-mode on")
        stop = self.index(" stop tenant-frontend")
        migrate = self.index(" migrate")
        self.assertLess(pull, backup)
        self.assertLess(dump, maintenance)
        self.assertLess(maintenance, stop)
        self.assertLess(stop, migrate)
        self.assertEqual(self.link("alpha", "backend-current"), f"releases/backend-{commit(2)[:12]}-b2")
        self.assertEqual(self.link("alpha", "backend-previous"), f"releases/backend-{commit(1)[:12]}-b1")
        backups = list((self.root / "alpha" / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "SHA256SUMS").is_file())

    def test_failed_migration_keeps_current_and_rolls_back(self):
        self.first_install()
        result = self.apply("alpha", self.backend(2), FAKE_FAIL=" migrate")
        self.assertNotEqual(result.returncode, 0)
        first = f"releases/backend-{commit(1)[:12]}-b1"
        second = f"releases/backend-{commit(2)[:12]}-b2"
        self.assertEqual(self.link("alpha", "backend-current"), first)
        self.assertEqual(self.link("alpha", "backend-pending"), second)
        self.assertEqual((self.root / "alpha" / "phase").read_text().strip(), "migrating")
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        down = self.index(" down --remove-orphans")
        self.assertIn(f"backend-{commit(2)[:12]}-b2", self.calls()[down])
        up = self.index("up --detach --wait")
        self.assertIn(f"backend-{commit(1)[:12]}-b1", self.calls()[up])
        self.assertLess(down, up)
        self.assertEqual(self.link("alpha", "backend-current"), first)
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())
        self.assertFalse(any("restore" in line for line in self.calls()))

    def test_rollback_with_restore_uses_the_backup_of_the_failed_release(self):
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL=" migrate")
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--restore-backup")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertLess(self.index("pg_restore"), self.index("--remove-orphans", self.index("pg_restore")))
        self.assertIn("restored", rolled.stdout)

    def test_rollback_of_a_current_release_returns_to_previous(self):
        self.first_install()
        self.assertEqual(self.apply("alpha", self.backend(2)).returncode, 0)
        rolled = self.run_remote("alpha", "rollback", "backend")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.link("alpha", "backend-current"), f"releases/backend-{commit(1)[:12]}-b1")
        self.assertEqual(self.link("alpha", "backend-previous"), f"releases/backend-{commit(2)[:12]}-b2")

    def test_prod_refuses_a_release_without_offsite_backup(self):
        self.first_install("prod")
        result = self.apply("prod", self.backend(2, "prod"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("offsite", result.stderr)
        self.assertFalse(any("set-maintenance-mode on" in line for line in self.calls()))
        self.assertEqual(self.link("prod", "backend-current"), f"releases/backend-{commit(1)[:12]}-b1")

    def test_status_reports_the_current_backend_release(self):
        self.first_install()
        status = self.run_remote("alpha", "status", "backend")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(status.stdout.strip(), f"backend-{commit(1)[:12]}-b1")

    def test_web_release_switches_links_and_rolls_back(self):
        first, first_bundle = self.web(1)
        second, second_bundle = self.web(2)
        self.assertEqual(self.apply("alpha", first, first_bundle).returncode, 0)
        result = self.apply("alpha", second, second_bundle)
        self.assertEqual(result.returncode, 0, result.stderr)
        web = self.root / "web" / "alpha"
        self.assertEqual(os.readlink(web / "current"), f"releases/{second['release_id']}")
        self.assertEqual(os.readlink(web / "previous"), f"releases/{first['release_id']}")
        asset = self.run_remote("alpha", "status", "web-asset")
        self.assertEqual(asset.stdout.strip(), "index-2.js")
        rolled = self.run_remote("alpha", "rollback", "web")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(os.readlink(web / "current"), f"releases/{first['release_id']}")
        self.assertEqual(self.calls(), [])

    def test_web_release_with_a_wrong_checksum_is_refused(self):
        manifest, (name, _) = self.web(1)
        result = self.apply("alpha", manifest, (name, b"changed"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr)
        self.assertFalse((self.root / "web" / "alpha" / "current").is_symlink())


if __name__ == "__main__":
    unittest.main()
