"""Tests for the server side scripts in deploy/remote with a fake docker command.

The fake docker writes every call to a log and runs nothing. The tests check the order of the
release steps, the links and the rollback. They need GNU tools (mv -T, sha256sum), so they run on
Linux, as the Jenkins agents and the servers do. On other systems they are skipped.
"""

import hashlib
import io
import json
import os
import re
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

DOMAIN = release.load_brand()["BRAND_DOMAIN"]
SITE = f"demo.app.alpha.{DOMAIN}"
import test_settings  # noqa: E402

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
*"site-settings-probe"*) printf '%s\n' "$FAKE_SITE_KEYS" ;;
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
            # The tenant image reports every site with every required setting (site-probe.py).
            "FAKE_SITE_KEYS": json.dumps({
                site: {"set": sorted(test_settings.required("tenant-site")), "differs": []}
                for settings in release.load_environments().values()
                for site in settings["ATONOTA_TENANT_SITES"].split()
            }),
        }
        # The DevOps owner wrote every secret file of every environment (blocker E-4).
        for env in release.ORDER:
            test_settings.fill_server(self.etc, env, press=True)
            keycloak = self.etc / env / "keycloak.env"
            keycloak.write_text(re.sub(r"(?m)^IDENTITY_BRAND_NAME=.*\n?", "", keycloak.read_text()))

    def incoming(self, env, manifest, bundle=None, drop=()):
        folder = self.folder / f"incoming-{env}-{manifest['release_id']}"
        # Jenkins sends the files again on every attempt.
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
        release.pack_deploy(DEPLOY, folder, manifest["commit"])
        packed = folder / "deploy"
        (folder / "release.json").write_text(json.dumps(manifest))
        shutil.copy(packed / "environments" / f"{env}.env", folder)
        for name in ("stack.yaml", "edge.yaml", "Caddyfile", "site.caddy.template"):
            shutil.copy(packed / "compose" / name, folder)
        for script in (packed / "remote").iterdir():
            if script.is_file():
                shutil.copy(script, folder)
        for listing in (packed / "settings").glob("*.production.env.example"):
            shutil.copy(listing, folder)
        if bundle:
            name, data = bundle
            (folder / name).write_bytes(data)
        for name in drop:
            (folder / name).unlink()
        return folder

    def run_script(self, path, *arguments, **extra):
        return subprocess.run(
            [str(path), *arguments],
            env={**self.environment, **extra},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )

    def apply(self, env, manifest, bundle=None, drop=(), press_enabled=None, **extra):
        folder = self.incoming(env, manifest, bundle, drop)
        if press_enabled is not None:
            # The environment file comes with the release; a test may turn its Press switch.
            env_file = folder / f"{env}.env"
            env_file.write_text(re.sub(r"(?m)^ATONOTA_PRESS_ENABLED=.*$",
                                       f"ATONOTA_PRESS_ENABLED={press_enabled}", env_file.read_text()))
        return self.run_script(folder / "apply", env, str(folder), **extra)

    def release_env(self, env, number):
        return (self.root / env / "releases" / f"backend-{commit(number)[:12]}-b{number}" / "release.env").read_text()

    def press_backend(self, number, env="alpha"):
        manifest = self.backend(number, env)
        manifest["components"]["press"] = {"image": f"ghcr.io/karacaismail/atonota-press@sha256:{number:064x}"}
        return manifest

    def run_remote(self, env, script, *arguments, **extra):
        # Server copies: backend scripts in <env>/bin, web scripts in web/<env>/bin.
        kind = arguments[0] if arguments else ""
        scripts = self.root / "web" / env / "bin" if kind.startswith("web") else self.root / env / "bin"
        return self.run_script(scripts / script, env, *arguments, **extra)

    def backend(self, number, env="alpha"):
        components = {
            name: {"image": f"ghcr.io/karacaismail/atonota-{name}@sha256:{number:064x}"}
            for name in ("tenant", "keycloak", "identity-sync")
        }
        if env in ("rc", "prod"):
            components["press"] = {"image": f"ghcr.io/karacaismail/atonota-press@sha256:{number:064x}"}
        return release.new_manifest("backend", commit(number), number, components)

    def web(self, number, vite_manifest=True, entry=None, chunk=None, extra=None, files=()):
        buffer = io.BytesIO()
        entry = entry or f"assets/index-{number}.js"
        files = [("index.html", b"<!doctype html>"), (f"assets/index-{number}.js", b"1"), *files]
        if vite_manifest:
            # The /panel page reads this file (E-3). Vite writes it with build.manifest.
            vite = {"index.html": {"file": entry, "isEntry": True, **(chunk or {})}, **(extra or {})}
            files.append((".vite/manifest.json", json.dumps(vite).encode()))
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, data in files:
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
        migrate = self.index(f"bench --site {SITE} migrate")
        start = self.index("--remove-orphans")
        reload = self.index("caddy reload")
        self.assertLess(pull, migrate)
        self.assertLess(migrate, start)
        self.assertLess(start, reload)
        self.assertFalse(any("backup" in line for line in self.calls()))
        self.assertEqual(self.link("alpha", "backend-current"), f"releases/backend-{commit(1)[:12]}-b1")
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())
        site = (self.root / "edge" / "sites" / "alpha.caddy").read_text()
        self.assertIn(f"api.login.alpha.{DOMAIN} {{", site)
        self.assertIn(f"{SITE} {{", site)
        self.assertIn("reverse_proxy alpha-keycloak:8080", site)
        self.assertNotIn("__", site)

    def release_link(self, number):
        return f"releases/backend-{commit(number)[:12]}-b{number}"

    def release_id(self, number):
        return f"backend-{commit(number)[:12]}-b{number}"

    def test_first_install_starts_again_after_the_site_was_created(self):
        # First install stops at "site does not exist"; the person creates the site and runs the
        # same command again. No release runs yet, so there is nothing to protect.
        first = self.apply("alpha", self.backend(1), ATONOTA_FIRST_INSTALL="1", FAKE_FAIL="list-apps")
        self.assertNotEqual(first.returncode, 0)
        self.assertIn("does not exist", first.stderr)
        # The first install steps also remove backend-pending before the second run.
        (self.root / "alpha" / "backend-pending").unlink()
        again = self.apply("alpha", self.backend(1), ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))

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

    def resume(self, env, **extra):
        return self.run_script(self.root / env / "backend-pending" / "bin" / "apply", env, "--resume", **extra)

    def folder_phase(self, env, number):
        return (self.root / env / "releases" / self.release_id(number) / "phase").read_text().strip()

    def test_same_release_again_after_a_failed_migration_waits_for_a_person(self):
        # A retry rewrote "migrating" to "preparing"; rollback then opened the old release on a
        # half migrated database (review 2, finding E3). The stopped tenant-web fails "exec".
        self.first_install("beta")
        self.apply("beta", self.backend(2, "beta"), FAKE_FAIL=" migrate")
        self.log.unlink()
        again = self.apply("beta", self.backend(2, "beta"), FAKE_FAIL="set-maintenance-mode on")
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("person", again.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.folder_phase("beta", 2), "migrating")
        rolled = self.run_remote("beta", "rollback", "backend", "--failed", self.release_id(2))
        self.assertNotEqual(rolled.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.link("beta", "backend-pending"), self.release_link(2))

    def test_failed_retry_never_frees_the_next_release(self):
        # A retry that failed while pulling let rollback drop the pending link (finding E3).
        self.first_install("beta")
        self.apply("beta", self.backend(2, "beta"), FAKE_FAIL=" migrate")
        self.apply("beta", self.backend(2, "beta"), FAKE_FAIL=" pull --quiet")
        self.run_remote("beta", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(self.link("beta", "backend-pending"), self.release_link(2))
        self.assertEqual(self.folder_phase("beta", 2), "migrating")
        self.log.unlink()
        third = self.apply("beta", self.backend(3, "beta"))
        self.assertNotEqual(third.returncode, 0)
        self.assertIn("pending", third.stderr)
        self.assertEqual(self.calls(), [])

    def test_retry_after_a_pull_failure_runs_again(self):
        # Before "stopping" the old release runs untouched, so the same release may start again.
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL=" pull --quiet")
        result = self.apply("alpha", self.backend(2))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(2))

    def test_resume_migrates_again_and_starts_the_pending_release(self):
        # The way out after a person finished or fixed the migration (finding E3).
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL=" migrate")
        backup = (self.root / "alpha" / "releases" / self.release_id(2) / "backup-before").read_text()
        self.log.unlink()
        result = self.resume("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertFalse(any(" stop " in line or "backup" in line or " pull" in line for line in calls), calls)
        self.assertFalse(any("set-maintenance-mode on" in line for line in calls), calls)
        migrate = self.index(f"bench --site {SITE} migrate")
        self.assertIn(self.release_id(2), calls[migrate])
        start = self.index("--wait-timeout 600 --remove-orphans")
        self.assertLess(migrate, start)
        self.assertLess(start, self.index("set-maintenance-mode off"))
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(2))
        self.assertEqual(self.link("alpha", "backend-previous"), self.release_link(1))
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())
        kept = (self.root / "alpha" / "releases" / self.release_id(2) / "backup-before").read_text()
        self.assertEqual(kept, backup)

    def test_resume_after_a_failed_start_skips_the_migration(self):
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL="--wait-timeout 600 --remove-orphans")
        self.log.unlink()
        result = self.resume("alpha")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(" migrate" in line for line in self.calls()), self.calls())
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(2))

    def test_resume_refuses_a_release_that_stopped_before_its_backup(self):
        # Without a backup the migration must not start; rollback starts the old release instead.
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL="backup --with-files")
        self.log.unlink()
        result = self.resume("alpha")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rollback", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.folder_phase("alpha", 2), "backing-up")

    def test_rolled_back_release_can_be_applied_again(self):
        # After a restore the database matches the backup, so a new attempt starts from the top.
        self.first_install()
        self.apply("alpha", self.backend(2), FAKE_FAIL=" migrate")
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2), "--restore-backup")
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.folder_phase("alpha", 2), "rolled-back")
        result = self.apply("alpha", self.backend(2))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(2))

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
        offsite = self.etc / "prod" / "offsite.env"
        test_settings.write_env(offsite, test_settings.filled("offsite"))
        self.first_install("prod")
        offsite.unlink()
        result = self.apply("prod", self.backend(2, "prod"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("offsite", result.stderr)
        self.assertFalse(any("set-maintenance-mode on" in line for line in self.calls()))
        self.assertEqual(self.link("prod", "backend-current"), f"releases/backend-{commit(1)[:12]}-b1")
        self.log.unlink(missing_ok=True)
        rolled = self.run_remote("prod", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.calls(), [], "prod keeps running; no restart (finding K6)")

    def test_offsite_backup_loads_settings_before_writing_the_site_brand(self):
        test_settings.write_env(self.etc / "prod/offsite.env", test_settings.filled("offsite"))
        rclone = self.folder / "bin/rclone"
        rclone.write_text('#!/usr/bin/env bash\nset -eu\n'
                          '[[ -n "$RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY" ]]\n'
                          'printf "%s\\n" "$1" >>"$FAKE_RCLONE_LOG"\n')
        rclone.chmod(0o755)
        self.first_install("prod")
        offsite_log = self.folder / "rclone.log"
        result = self.apply("prod", self.backend(2, "prod"), FAKE_RCLONE_LOG=str(offsite_log))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(offsite_log.read_text().splitlines(), ["copy", "check"])
        backup = self.index("backup --with-files")
        brand = self.index("set-config -- identity_brand_name")
        migrate = self.index(" migrate", start=brand)
        self.assertLess(backup, brand)
        self.assertLess(brand, migrate)

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

    def test_web_release_needs_a_manifest_that_names_a_bundled_entry(self):
        for name, (manifest, bundle) in {
            "no manifest": self.web(1, vite_manifest=False),
            "entry not in the bundle": self.web(1, entry="assets/missing.js"),
            "entry outside assets": self.web(1, entry="../index-1.js"),
        }.items():
            with self.subTest(name):
                result = self.apply("alpha", manifest, bundle)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifest", result.stderr)
                self.assertFalse((self.root / "web" / "alpha" / "current").exists())
                self.assertFalse((self.root / "web" / "alpha" / "releases" / manifest["release_id"]).exists())

    def test_web_release_checks_styles_and_imports_like_the_panel_page(self):
        # platform_core/shell/panel_assets.py refuses these names, so /panel would show the
        # placeholder after the release (review 1, K-1). The release is refused instead.
        css = ("assets/index-1.css", b"a{}")
        vendor = ("assets/vendor-1.js", b"2")
        for name, (manifest, bundle) in {
            "style in a sub folder": self.web(1, chunk={"css": ["assets/sub/a.css"]}, files=[("assets/sub/a.css", b"")]),
            "style is not css": self.web(1, chunk={"css": ["assets/index-1.js"]}),
            "style not in the bundle": self.web(1, chunk={"css": ["assets/missing.css"]}),
            "css is not a list": self.web(1, chunk={"css": "assets/index-1.css"}, files=[css]),
            "import has no chunk": self.web(1, chunk={"imports": ["_vendor.js"]}),
            "import outside assets": self.web(
                1, chunk={"imports": ["_vendor.js"]}, extra={"_vendor.js": {"file": "../vendor-1.js"}}
            ),
            "style of an import in a sub folder": self.web(
                1,
                chunk={"imports": ["_vendor.js"]},
                extra={"_vendor.js": {"file": "assets/vendor-1.js", "css": ["assets/x/b.css"]}},
                files=[vendor],
            ),
            "entry flag missing": self.web(1, chunk={"isEntry": False}),
        }.items():
            with self.subTest(name):
                result = self.apply("alpha", manifest, bundle)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifest", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse((self.root / "web" / "alpha" / "current").exists())
        manifest, bundle = self.web(
            1,
            chunk={"css": ["assets/index-1.css"], "imports": ["_vendor.js"]},
            extra={"_vendor.js": {"file": "assets/vendor-1.js", "imports": ["index.html"]}},
            files=[css, vendor],
        )
        result = self.apply("alpha", manifest, bundle)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_remote("alpha", "status", "web-asset").stdout.strip(), "index-1.js")

    def test_web_release_keeps_the_backend_scripts_of_the_server(self):
        # Scripts come from each release's own commit (Ö8). An older web release must not put its
        # older rollback where the backend rollback runs from.
        self.first_install()
        backend_rollback = self.root / "alpha" / "bin" / "rollback"
        backend_rollback.write_text(backend_rollback.read_text() + "# backend copy\n")
        manifest, bundle = self.web(1)
        self.assertEqual(self.apply("alpha", manifest, bundle).returncode, 0)
        self.assertTrue(backend_rollback.read_text().endswith("# backend copy\n"))
        self.assertTrue((self.root / "web" / "alpha" / "bin" / "rollback").is_file())

    def test_web_release_with_a_wrong_checksum_is_refused(self):
        manifest, (name, _) = self.web(1)
        result = self.apply("alpha", manifest, (name, b"changed"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr)
        self.assertFalse((self.root / "web" / "alpha" / "current").is_symlink())

    # Production settings (blocker E-4): a missing setting stops the release before any change.

    def test_missing_secret_key_stops_before_any_change(self):
        self.first_install()
        values = test_settings.filled("keycloak")
        del values["KC_DB_PASSWORD"]
        test_settings.write_env(self.etc / "alpha" / "keycloak.env", values)
        result = self.apply("alpha", self.backend(2))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("keycloak.env: KC_DB_PASSWORD (missing)", result.stderr)
        self.assertIn("nothing changed", result.stderr)
        self.assertNotIn("fake-value-for-tests", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.root / "alpha" / "backend-pending").is_symlink())
        self.assertFalse((self.root / "alpha" / "releases" / self.release_id(2)).exists())
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))

    def test_missing_secret_file_stops_the_first_install(self):
        (self.etc / "alpha" / "tenant.env").unlink()
        result = self.apply("alpha", self.backend(1), ATONOTA_FIRST_INSTALL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{self.etc}/alpha/tenant.env: file is missing", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_release_with_press_needs_the_press_file(self):
        (self.etc / "alpha" / "press.env").unlink()
        result = self.apply("alpha", self.press_backend(1), press_enabled=1, ATONOTA_FIRST_INSTALL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("press.env: file is missing", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_press_image_without_the_switch_keeps_press_off(self):
        # Review finding B1: a release always carries the Press image. Press starts only after the
        # first install opened the Press site and set ATONOTA_PRESS_ENABLED=1.
        (self.etc / "alpha" / "press.env").unlink()
        result = self.apply("alpha", self.press_backend(1), ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_PROFILES=\n", self.release_env("alpha", 1))
        self.assertIn("ATONOTA_IMAGE_PRESS=", self.release_env("alpha", 1))

    def test_press_switch_turns_the_press_profile_on(self):
        result = self.apply("alpha", self.press_backend(1), press_enabled=1, ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_PROFILES=press\n", self.release_env("alpha", 1))

    def test_press_switch_without_a_press_image_keeps_press_off(self):
        result = self.apply("alpha", self.backend(1), press_enabled=1, ATONOTA_FIRST_INSTALL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_PROFILES=\n", self.release_env("alpha", 1))

    def test_server_refuses_the_press_switch_in_rc_and_prod(self):
        # Review 1, finding 5: release.py refuses ATONOTA_PRESS_ENABLED=1 in rc and prod on the
        # Jenkins side. A person may run apply on the server by hand, so the server checks again.
        for env in ("rc", "prod"):
            with self.subTest(env=env):
                # Every other setting is complete, so only the Press switch can stop the release.
                test_settings.fill_server(self.etc, env, press=True, offsite=True)
                result = self.apply(env, self.backend(1, env), press_enabled=1, ATONOTA_FIRST_INSTALL="1")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"ATONOTA_PRESS_ENABLED=1 is refused in {env}", result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse((self.root / env / "releases").exists())

    def test_missing_site_setting_stops_while_the_old_release_runs(self):
        self.first_install()
        keys = [key for key in test_settings.required("tenant-site") if key != "keycloak_client_secret"]
        result = self.apply("alpha", self.backend(2),
                            FAKE_SITE_KEYS=json.dumps({SITE: {"set": keys, "differs": []}}))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{SITE}, site_config.json: keycloak_client_secret (missing)",
                      result.stderr)
        self.assertLess(self.index(" pull --quiet"), self.index("site-settings-probe"))
        self.assertFalse(any("set-maintenance-mode" in line or " stop " in line for line in self.calls()))
        self.assertEqual(self.link("alpha", "backend-current"), self.release_link(1))
        # The release stopped in phase pulling, so the automatic rollback leaves the old one alone.
        self.log.unlink()
        rolled = self.run_remote("alpha", "rollback", "backend", "--failed", self.release_id(2))
        self.assertEqual(rolled.returncode, 0, rolled.stderr)
        self.assertEqual(self.calls(), [])

    def test_developer_mode_on_a_site_stops_while_the_old_release_runs(self):
        self.first_install()
        report = {"set": sorted(test_settings.required("tenant-site")), "differs": ["developer_mode"]}
        result = self.apply("alpha", self.backend(2),
                            FAKE_SITE_KEYS=json.dumps({SITE: report}))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("developer_mode (must be 0)", result.stderr)
        probe = self.calls()[self.index("site-settings-probe")]
        self.assertIn('"developer_mode": "0"', probe)
        # The image entrypoint prints to stdout and relinks the assets of the running release.
        self.assertIn("--entrypoint /home/frappe/frappe-bench/env/bin/python tenant-web -I -", probe)
        self.assertFalse(any("set-maintenance-mode" in line for line in self.calls()))

    def test_missing_site_after_the_first_install_stops_before_the_old_release_stops(self):
        self.first_install()
        result = self.apply("alpha", self.backend(2), FAKE_SITE_KEYS="{}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist", result.stderr)
        self.assertFalse(any("set-maintenance-mode" in line for line in self.calls()))

    def test_release_keeps_the_lists_it_was_checked_with(self):
        self.first_install()
        folder = self.root / "alpha" / "releases" / self.release_id(1)
        names = {path.name for path in (folder / "settings").iterdir()}
        self.assertIn("keycloak.production.env.example", names)
        probe = json.loads((folder / "site-settings.json").read_text())
        self.assertIn(SITE, probe)


if __name__ == "__main__":
    unittest.main()
