"""Tests for the release manifest and the promotion rules (docs/dagitim/ortamlar.md).

Run from the repository root:
    python3 -I -m unittest discover -s backend/deploy/tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import release  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "a" * 64


def image(name):
    return f"ghcr.io/karacaismail/atonota-{name}@{DIGEST}"


def backend_manifest(**overrides):
    components = {name: {"image": image(name)} for name in release.REQUIRED["backend"]}
    manifest = release.new_manifest("backend", COMMIT, 7, components)
    manifest.update(overrides)
    return manifest


def web_manifest():
    return release.new_manifest(
        "web",
        COMMIT,
        3,
        {"panel": {"file": f"atonota-web-{COMMIT[:12]}.tar.gz", "sha256": "b" * 64}},
    )


class EnvironmentFiles(unittest.TestCase):
    def test_four_environments_form_one_chain(self):
        environments = release.load_environments()
        self.assertEqual(list(environments), ["alpha", "beta", "rc", "prod"])
        self.assertEqual(
            [environments[name]["ATONOTA_PREVIOUS_ENV"] for name in environments],
            ["", "alpha", "beta", "rc"],
        )

    def test_host_names_follow_the_domain_map(self):
        for name, settings in release.load_environments().items():
            base = "atonota.net" if name == "prod" else f"{name}.atonota.net"
            self.assertEqual(settings["ATONOTA_BASE_HOST"], base)
            self.assertEqual(settings["ATONOTA_ID_HOST"], f"id.{base}")
            self.assertEqual(settings["ATONOTA_PRESS_HOST"], f"press.{base}")
            self.assertEqual(settings["ATONOTA_TENANT_ZONE"], f"app.{base}")
            for site in settings["ATONOTA_TENANT_SITES"].split():
                self.assertTrue(site.endswith("." + settings["ATONOTA_TENANT_ZONE"]), site)

    def test_prod_keycloak_host_stays_as_recorded(self):
        # PROJECT-RECORD.md O-1.
        self.assertEqual(release.load_environments()["prod"]["ATONOTA_ID_HOST"], "id.atonota.net")

    def test_release_candidate_and_prod_are_strict(self):
        environments = release.load_environments()
        for name in ("rc", "prod"):
            self.assertEqual(environments[name]["ATONOTA_REQUIRE_ALL_COMPONENTS"], "1")
            self.assertEqual(environments[name]["ATONOTA_REQUIRE_OFFSITE_BACKUP"], "1")
            self.assertEqual(environments[name]["ATONOTA_AUTO_RESTORE_ON_FAILURE"], "0")

    def test_prod_has_its_own_server(self):
        environments = release.load_environments()
        others = {environments[name]["ATONOTA_SSH_HOST"] for name in ("alpha", "beta", "rc")}
        self.assertNotIn(environments["prod"]["ATONOTA_SSH_HOST"], others)
        self.assertNotEqual(environments["rc"]["ATONOTA_SSH_HOST"], environments["beta"]["ATONOTA_SSH_HOST"])

    def test_each_environment_has_its_own_server_user(self):
        # A key of one environment never logs in as the user of another (review 1, finding 6).
        environments = release.load_environments()
        for name, settings in environments.items():
            self.assertEqual(settings["ATONOTA_SSH_USER"], f"deploy-{name}")

    def test_environment_files_hold_no_secret(self):
        for path in sorted((DEPLOY / "environments").glob("*.env")):
            for key in release.parse_env_file(path):
                self.assertIsNone(release.SECRET_KEY.search(key), f"{path.name}: {key}")

    def test_unknown_key_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alpha.env"
            path.write_text("ATONOTA_ENV=alpha\nATONOTA_DB_PASSWORD=x\n")
            with self.assertRaises(release.ReleaseError):
                release.parse_env_file(path)


class Manifest(unittest.TestCase):
    def test_valid_backend_manifest_passes_every_environment(self):
        manifest = backend_manifest()
        self.assertEqual(manifest["release_id"], f"backend-{COMMIT[:12]}-b7")
        for name in ("alpha", "beta", "rc", "prod"):
            release.check_manifest(manifest, name)

    def test_valid_web_manifest_passes(self):
        release.check_manifest(web_manifest(), "prod")

    def test_image_must_be_pinned_by_digest(self):
        manifest = backend_manifest()
        manifest["components"]["tenant"]["image"] = "ghcr.io/karacaismail/atonota-tenant:latest"
        with self.assertRaisesRegex(release.ReleaseError, "digest"):
            release.check_manifest(manifest, "alpha")

    def test_missing_component_is_allowed_before_rc_only(self):
        manifest = backend_manifest()
        del manifest["components"]["press"]
        release.check_manifest(manifest, "alpha")
        release.check_manifest(manifest, "beta")
        for name in ("rc", "prod"):
            with self.assertRaisesRegex(release.ReleaseError, "press"):
                release.check_manifest(manifest, name)

    def test_unknown_component_is_refused(self):
        manifest = backend_manifest()
        manifest["components"]["shell"] = {"image": image("shell")}
        with self.assertRaises(release.ReleaseError):
            release.check_manifest(manifest, "alpha")

    def test_release_id_must_match_commit_and_build(self):
        manifest = backend_manifest(release_id="backend-ffffffffffff-b7")
        with self.assertRaisesRegex(release.ReleaseError, "release_id"):
            release.check_manifest(manifest, "alpha")

    def test_build_must_be_a_positive_whole_number(self):
        # A build field like "1;touch${IFS}/tmp/pwned" once passed, because release_id was only
        # rebuilt from the same fields (review 1, finding 1).
        for build in ("1;touch${IFS}/tmp/pwned", "7", True, 0, -1, 7.0):
            manifest = backend_manifest(build=build)
            manifest["release_id"] = release.release_id("backend", COMMIT, build)
            with self.subTest(build=build), self.assertRaisesRegex(release.ReleaseError, "build"):
                release.check_manifest(manifest, "beta")

    def test_release_id_must_be_plain(self):
        manifest = backend_manifest(release_id=f"backend-{COMMIT[:12]}-b7 x")
        with self.assertRaises(release.ReleaseError):
            release.check_manifest(manifest, "alpha")

    def test_commit_must_be_full(self):
        with self.assertRaises(release.ReleaseError):
            release.new_manifest("backend", "abc123", 1, {})


class Promotion(unittest.TestCase):
    def record(self, manifest, environment="alpha", healthy=True):
        return {
            "environment": environment,
            "kind": manifest["kind"],
            "release_id": manifest["release_id"],
            "healthy": healthy,
        }

    def test_same_healthy_release_moves_one_step(self):
        manifest = backend_manifest()
        release.check_promotion(manifest, "beta", self.record(manifest))
        release.check_promotion(manifest, "rc", self.record(manifest, "beta"))
        release.check_promotion(manifest, "prod", self.record(manifest, "rc"))

    def test_alpha_is_never_a_promotion_target(self):
        manifest = backend_manifest()
        with self.assertRaises(release.ReleaseError):
            release.check_promotion(manifest, "alpha", self.record(manifest))

    def test_step_cannot_be_skipped(self):
        manifest = backend_manifest()
        with self.assertRaisesRegex(release.ReleaseError, "rc"):
            release.check_promotion(manifest, "prod", self.record(manifest, "beta"))

    def test_unhealthy_source_is_refused(self):
        manifest = backend_manifest()
        with self.assertRaisesRegex(release.ReleaseError, "health"):
            release.check_promotion(manifest, "beta", self.record(manifest, healthy=False))

    def test_other_release_in_source_is_refused(self):
        manifest = backend_manifest()
        record = self.record(manifest)
        record["release_id"] = f"backend-{COMMIT[:12]}-b6"
        with self.assertRaisesRegex(release.ReleaseError, "release"):
            release.check_promotion(manifest, "beta", record)

    def test_kind_must_match(self):
        manifest = backend_manifest()
        record = self.record(manifest)
        record["kind"] = "web"
        with self.assertRaises(release.ReleaseError):
            release.check_promotion(manifest, "beta", record)


class CommandLine(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-I", str(DEPLOY / "release.py"), *arguments],
            capture_output=True,
            text=True,
        )

    def test_new_check_and_promote_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "release.json"
            created = self.run_cli(
                "new", "--kind", "backend", "--commit", COMMIT, "--build", "9", "--out", str(path),
                *(f"--image={name}={image(name)}" for name in release.REQUIRED["backend"]),
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertEqual(self.run_cli("check", str(path), "--env", "prod").returncode, 0)
            record = Path(folder) / "alpha.json"
            made = self.run_cli("record", str(path), "--env", "alpha", "--out", str(record))
            self.assertEqual(made.returncode, 0, made.stderr)
            moved = self.run_cli("promote-check", str(path), "--target", "beta", "--source-record", str(record))
            self.assertEqual(moved.returncode, 0, moved.stderr)
            skipped = self.run_cli("promote-check", str(path), "--target", "rc", "--source-record", str(record))
            self.assertEqual(skipped.returncode, 1)
            self.assertIn("beta", skipped.stderr)

    def test_same_release_accepts_only_an_identical_manifest(self):
        # promote.Jenkinsfile compares the server copy with the copy Jenkins archived (finding 1).
        with tempfile.TemporaryDirectory() as folder:
            archived = Path(folder) / "archived.json"
            server = Path(folder) / "server.json"
            archived.write_text(json.dumps(backend_manifest(), indent=2))
            server.write_text(json.dumps(backend_manifest()))
            same = self.run_cli("same-release", str(archived), str(server))
            self.assertEqual(same.returncode, 0, same.stderr)
            changed = backend_manifest()
            changed["components"]["tenant"]["image"] = image("tenant").replace("a" * 64, "c" * 64)
            server.write_text(json.dumps(changed))
            other = self.run_cli("same-release", str(archived), str(server))
            self.assertEqual(other.returncode, 1)
            self.assertIn("differs", other.stderr)

    def test_field_prints_one_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "release.json"
            path.write_text(json.dumps(backend_manifest()))
            printed = self.run_cli("field", str(path), "release_id")
            self.assertEqual(printed.stdout.strip(), f"backend-{COMMIT[:12]}-b7")


if __name__ == "__main__":
    unittest.main()
