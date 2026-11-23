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
*" config --services"*) printf '%s\n' ${FAKE_SERVICES:-tenant-web keycloak identity-sync} ;;
*" ps --all --format"*) printf '%b' "${FAKE_PS:-tenant-web running healthy\nkeycloak running healthy\nidentity-sync running \n}" ;;
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

    def incoming(self, env, manifest, bundle=None, drop=()):
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
        for name in drop:
            (folder / name).unlink()
        return folder

    def apply(self, env, manifest, bundle=None, drop=(), **extra):
        folder = self.incoming(env, manifest, bundle, drop)
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

    def release_link(self, number):
        return f"releases/backend-{commit(number)[:12]}-b{number}"

    def release_id(self, number):
        return f"backend-{commit(number)[:12]}-b{number}"

    def test_next_release_stops_writers_before_the_backup(self):
        # Writes between the backup and the stop were lost on restore (review 1, finding 3).
        self.first_install()
        result = self.apply("alpha", self.backend(2))
        self.assertEqual(result.returncode, 0, result.stderr)
        pull = self.index(" pull --quiet")
        maintenance = self.index("set-maintenance-mode on")
        stop = self.index(" stop tenant-frontend")
        backup = self.index("backup --with-files")
        dump = self.index("pg_dump")
        sync_backup = self.index("identity_sync.sqlite3")
        stop_web = self.index(" stop tenant-web")
        migrate = self.index(" migrate")
        self.assertLess(pull, maintenance)
        self.assertLess(maintenance, stop)
        for writer in ("tenant-worker", "tenant-socket", "identity-sync", "keycloak"):
            self.assertIn(writer, self.calls()[stop])
        self.assertLess(stop, backup)
        self.assertLess(stop, dump)
        self.assertLess(stop, sync_backup)
        self.assertNotIn(" exec ", self.calls()[sync_backup], "identity-sync is stopped; use run")
        self.assertLess(max(backup, dump, sync_backup), stop_web)
        self.assertLess(stop_web, migrate)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(2))
        self.assertEqual(self.link("alpha", "backend-previous"), self.release_link(1))
        backups = list((self.root / "alpha" / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertTrue((backups[0] / "SHA256SUMS").is_file())

    def test_early_failure_never_rolls_back_the_healthy_release(self):
        # The release never reached the server whole; the running one is healthy (finding E1).
        self.first_install()
        result = self.apply("alpha", self.backend(2), drop=("Caddyfile",))
        self.assertNotEqual(result.returncode, 0)
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2), "--restore-backup")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertIn("nothing to roll back", rolled.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))

    def test_pull_failure_keeps_the_old_release_open_without_restore(self):
        # No backup exists yet, so nothing is restored and nothing is stopped (finding E2).
        self.first_install()
        result = self.apply("alpha", self.backend(2), FAKE_FAIL=" pull --quiet")
        self.assertNotEqual(result.returncode, 0)
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2), "--restore-backup")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertFalse(any(" down" in line or "restore" in line for line in self.calls()), self.calls())
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())

    def test_failure_while_stopped_starts_the_old_release_again(self):
        # Prod without its offsite copy stops in the backup step (finding K6): no down, no restore.
        self.first_install()
        result = self.apply("alpha", self.backend(2), FAKE_FAIL="backup --with-files")
        self.assertNotEqual(result.returncode, 0)
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2), "--restore-backup")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertFalse(any(" down" in line or "pg_restore" in line for line in self.calls()), self.calls())
        up = self.index("up --detach --wait")
        self.assertIn(self.release_id(1), self.calls()[up])
        self.assertLess(up, self.index("set-maintenance-mode off"))
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))

    def test_failed_migration_without_restore_waits_for_a_person(self):
        # A half migrated database must not open to users (finding 2).
        self.first_install("beta")
        result = self.apply("beta", self.backend(2, "beta"), FAKE_FAIL=" migrate")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.link("beta", "backend-pending"), self.release_link(2))
        self.assertEqual((self.root / "beta" / "phase").read_text().split()[0], "migrating")
        self.log.unlink()
        rolled = self.run_remote("beta", "rollback", "backend", "--failed", self.release_id(2))
        self.assertNotEqual(rolled.returncode, 0)
        self.assertIn("person", rolled.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.link("beta", "backend-pending"), self.release_link(2))

    def test_failed_migration_with_restore_uses_the_backup_of_the_failed_release(self):
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL=" migrate")
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2), "--restore-backup")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        down = self.index(" down --remove-orphans")
        restore = self.index("pg_restore")
        up = self.index("--remove-orphans", restore)
        self.assertLess(down, restore)
        self.assertIn(self.release_id(1), self.calls()[up])
        self.assertIn("restored", rolled.stdout)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))
        self.assertEqual(self.link("alpha", "backend-failed"), self.release_link(2))
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())

    def test_missing_backup_stops_before_anything_goes_down(self):
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL=" migrate")
        (self.root / "alpha" / "releases" / self.release_id(2) / "backup-before").unlink()
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2), "--restore-backup")
        self.assertNotEqual(rolled.returncode, 0)
        self.assertIn("no backup", rolled.stderr)
        self.assertEqual(self.calls(), [])

    def test_failed_start_after_migration_returns_to_the_old_images(self):
        # Migrations follow the expand and contract rule, so the old release runs on the new schema.
        self.first_install("beta")
        result = self.apply("beta", self.backend(2, "beta"), FAKE_FAIL="--wait-timeout 600 --remove-orphans")
        self.assertNotEqual(result.returncode, 0)
        self.log.unlink()
        rolled = self.run_remote("beta", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        up = self.index("up --detach --wait")
        self.assertIn(self.release_id(1), self.calls()[up])
        self.assertLess(up, self.index("set-maintenance-mode off"))
        self.assertEqual(self.link("beta", "backend-current"), self.release_link(1))

    def test_failed_health_check_rolls_back_the_new_current_release(self):
        self.first_install()
        self.assertEqual(self.apply("alpha", self.backend(2)).returncode, 0)
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))
        self.assertEqual(self.link("alpha", "backend-failed"), self.release_link(2))

    def test_release_with_a_passed_health_check_is_not_rolled_back_automatically(self):
        self.first_install()
        self.assertEqual(self.apply("alpha", self.backend(2)).returncode, 0)
        record = {"environment": "alpha", "kind": "backend", "release_id": self.release_id(2), "healthy": True}
        (self.root / "alpha" / "health" / "backend.json").write_text(json.dumps(record))
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertIn("nothing to roll back", rolled.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(2))

    def test_rollback_of_a_current_release_returns_to_previous(self):
        self.first_install()
        self.assertEqual(self.apply("alpha", self.backend(2)).returncode, 0)
        rolled = self.run_remote("alpha", "rollback", "backend")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))
        self.assertEqual(self.link("alpha", "backend-failed"), self.release_link(2))

    def test_second_rollback_never_returns_to_the_failed_release(self):
        # The failed release once became "previous", so a second rollback went back to it (finding 4).
        self.first_install()
        self.assertEqual(self.apply("alpha", self.backend(2)).returncode, 0)
        self.assertEqual(self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2)).returncode, 0)
        again = self.run_remote("alpha", "rollback", "backend")
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))

    def test_new_release_waits_while_another_one_is_pending(self):
        self.first_install("beta")
        self.apply("beta", self.backend(2, "beta"), FAKE_FAIL=" migrate")
        self.log.unlink()
        result = self.apply("beta", self.backend(3, "beta"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pending", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.link("beta", "backend-pending"), self.release_link(2))

    def test_status_sees_a_stopped_service(self):
        # "ps" without --all hid an exited identity-sync (finding 5).
        self.first_install()
        stopped = self.run_remote(
            "alpha", "status", "backend", FAKE_PS="tenant-web running healthy\\nkeycloak running healthy\\nidentity-sync exited \\n"
        )
        self.assertNotEqual(stopped.returncode, 0)
        self.assertIn("identity-sync", stopped.stderr)
        missing = self.run_remote("alpha", "status", "backend", FAKE_PS="tenant-web running healthy\\n")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("keycloak", missing.stderr)

    def test_each_environment_has_its_own_edge_network(self):
        # alpha containers could reach beta Keycloak over one shared network (finding K2).
        self.first_install("alpha")
        result = self.apply("beta", self.backend(1, "beta"), ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.index("network create atonota-edge-beta")
        networks = (self.root / "edge" / "networks.yaml").read_text()
        self.assertIn("name: atonota-edge-alpha", networks)
        self.assertIn("name: atonota-edge-beta", networks)
        stack = (DEPLOY / "compose" / "stack.yaml").read_text()
        self.assertIn("name: atonota-edge-${ATONOTA_ENV:?}", stack)

    def test_prod_refuses_a_release_without_offsite_backup(self):
        self.first_install("prod")
        result = self.apply("prod", self.backend(2, "prod"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("offsite", result.stderr)
        self.assertFalse(any("set-maintenance-mode on" in line for line in self.calls()))
        self.assertEqual(self.link("prod", "backend-current"), f"releases/backend-{commit(1)[:12]}-b1")
        self.log.unlink(missing_ok=True)
        rolled = self.run_remote("prod", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.calls(), [], "prod keeps running; no restart (finding K6)")

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
