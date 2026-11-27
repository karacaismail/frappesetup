"""Brand contract: AJA-1059 plan, one setting and release-owned environment output."""

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import release  # noqa: E402


class BrandDeployment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "backend" / "deploy"
        shutil.copytree(
            DEPLOY, self.source, ignore=shutil.ignore_patterns("__pycache__", "tests")
        )
        self.brand_file = self.source.parent / "brand.env"
        self.write_brand("Example Login", "example.test")

    def write_brand(self, product, domain):
        self.brand_file.write_text(
            f"PRODUCT_NAME={product}\nBRAND_DOMAIN={domain}\n", encoding="utf-8"
        )

    def pack(self, name):
        folder = self.root / name
        release.pack_deploy(self.source, folder, "a" * 40)
        return folder / "deploy"

    def read_host(self, packed, env):
        result = subprocess.run(
            [
                "bash",
                "-c",
                '. "$1"; load_host_env "$2"; python3 -c '
                "'import os,json; print(json.dumps(dict(os.environ)))'",
                "brand-test",
                str(packed / "remote" / "common.sh"),
                str(packed / "environments" / f"{env}.env"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def test_brand_changes_every_environment_in_new_release_only(self):
        first = self.pack("first")
        self.write_brand("Second Login", "second.test")
        second = self.pack("second")
        for packed, domain, product in (
            (first, "example.test", "Example Login"),
            (second, "second.test", "Second Login"),
        ):
            for env in ("alpha", "beta", "rc", "prod"):
                with self.subTest(release=packed.parent.name, env=env):
                    actual = self.read_host(packed, env)
                    base = domain if env == "prod" else f"{env}.{domain}"
                    self.assertEqual(actual["ATONOTA_BASE_HOST"], base)
                    self.assertEqual(actual["ATONOTA_ID_HOST"], f"api.login.{base}")
                    self.assertEqual(actual["ATONOTA_PRESS_HOST"], f"press.{base}")
                    self.assertEqual(actual["ATONOTA_TENANT_ZONE"], f"app.{base}")
                    self.assertEqual(actual["ATONOTA_TENANT_SITES"], f"demo.app.{base}")
                    self.assertEqual(actual["PRODUCT_NAME"], product)

    def test_display_name_is_data_in_both_shell_readers(self):
        marker = self.root / "executed"
        product = f"Example's Login $UNSET `touch {marker}` $(touch {marker}) # title\\"
        self.write_brand(product, "example.test")
        packed = self.pack("quoted")
        self.assertEqual(self.read_host(packed, "alpha")["PRODUCT_NAME"], product)
        result = subprocess.run(
            [
                "bash",
                "-c",
                '. "$1"; load_env alpha; printf "%s" "$PRODUCT_NAME"',
                "brand-test",
                str(self.source / "bin" / "lib.sh"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, product)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is not installed")
    def test_compose_reads_display_name_without_interpolation(self):
        product = "Örnek's Login $UNSET ${UNSET} # title\\"
        self.write_brand(product, "example.test")
        packed = self.pack("compose")
        compose = self.root / "compose.yaml"
        compose.write_text(
            "services:\n  test:\n    image: example.invalid/test\n"
            "    environment:\n      NAME: ${PRODUCT_NAME:?}\n"
        )
        command = ["docker"]
        if sys.platform == "darwin":
            command += ["--context", "colima-factory"]
        result = subprocess.run(
            command
            + [
                "compose",
                "--env-file",
                str(packed / "environments/alpha.env"),
                "-f",
                str(compose),
                "config",
                "--environment",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"PRODUCT_NAME={product}", result.stdout.splitlines())

    def test_reader_rejects_incomplete_ambiguous_or_unsafe_settings(self):
        load_brand = importlib.import_module("brand").load_brand
        for content in (
            "PRODUCT_NAME=Example\n",
            "PRODUCT_NAME=Example\nBRAND_DOMAIN=x.test\nEXTRA=x\n",
            "PRODUCT_NAME=Example\nPRODUCT_NAME=Other\nBRAND_DOMAIN=x.test\n",
            "PRODUCT_NAME=\nBRAND_DOMAIN=x.test\n",
            "PRODUCT_NAME=Example\nBRAND_DOMAIN=https://x.test/path\n",
            "PRODUCT_NAME=Example\nBRAND_DOMAIN=$(touch x)\n",
            "PRODUCT_NAME=Example\nBRAND_DOMAIN=-bad.test\n",
            "PRODUCT_NAME=Example\nBRAND_DOMAIN=x..test\n",
        ):
            with self.subTest(content=content):
                self.brand_file.write_text(content)
                with self.assertRaises(ValueError):
                    load_brand(self.brand_file)

    def test_reader_preserves_spaces_and_unicode(self):
        self.write_brand("Örnek Giriş", "example.test")
        self.assertEqual(
            importlib.import_module("brand").load_brand(self.brand_file),
            {"PRODUCT_NAME": "Örnek Giriş", "BRAND_DOMAIN": "example.test"},
        )

    def test_missing_brand_stops_before_release_output(self):
        self.brand_file.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.pack("missing")
        self.assertFalse((self.root / "missing" / "deploy").exists())

    def test_pack_supplies_brand_to_keycloak_and_site_contract(self):
        packed = self.pack("contract")
        self.assertIn(
            "IDENTITY_BRAND_NAME: ${PRODUCT_NAME:?",
            (packed / "compose/stack.yaml").read_text(),
        )
        keycloak = (packed / "settings/keycloak.production.env.example").read_text()
        self.assertNotIn("\nIDENTITY_BRAND_NAME=", keycloak)
        tenant = (packed / "settings/tenant-site.production.env.example").read_text()
        self.assertIn("identity_brand_name=Example Login", tenant)

    def test_site_brand_conflict_stops_but_missing_value_can_be_written(self):
        sys.path.insert(0, str(DEPLOY / "remote"))
        settings = importlib.import_module("settings")
        packed = self.pack("site-check")
        lists = packed / "settings"
        required = [
            entry.key
            for entry in settings.parse_list(
                lists / "tenant-site.production.env.example"
            )
            if not entry.optional
        ]
        site = "demo.app.alpha.example.test"
        probe = {site: {"set": required, "differs": []}}
        self.assertEqual(settings.check_sites(lists, probe, [site]), [])
        probe[site]["set"].append("identity_brand_name")
        probe[site]["differs"].append("identity_brand_name")
        self.assertTrue(
            any(
                "identity_brand_name" in problem
                for problem in settings.check_sites(lists, probe, [site])
            )
        )

    def test_duplicate_keycloak_brand_in_server_file_is_rejected(self):
        import test_settings

        packed = self.pack("keycloak-check")
        etc = self.root / "etc"
        test_settings.fill_server(etc, "alpha")
        settings = test_settings.settings
        issues = settings.check_files("alpha", packed / "settings", etc)
        self.assertTrue(
            any("remove IDENTITY_BRAND_NAME" in problem for problem in issues)
        )

    def test_deployment_scope_has_no_hardcoded_brand(self):
        import test_brand_hardcode as scanner

        root, files = scanner.tracked_files()
        files = [
            name
            for name in files
            if name.startswith("backend/deploy/")
            or name == "backend/dev/Dockerfile.tenant"
        ]
        self.assertEqual(
            scanner.find_hits(
                root,
                files,
                scanner.read_brand(scanner.BRAND_ENV),
                scanner.read_exclusions(scanner.EXCLUSIONS),
            ),
            [],
        )

    def test_offsite_settings_still_load_without_executing_values(self):
        settings_file = self.root / "offsite.env"
        settings_file.write_text(
            "RCLONE_CONFIG_OFFSITE_TYPE=s3\n"
            "RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY='fake-$UNSET'\n"
        )
        result = subprocess.run(
            [
                "bash",
                "-c",
                '. "$1"; load_host_env "$2"; printf "%s" "$RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY"',
                "brand-test",
                str(self.source / "remote/common.sh"),
                str(settings_file),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "fake-$UNSET")

    def test_health_uses_running_release_hosts_after_checkout_brand_changes(self):
        packed = self.pack("health")
        self.write_brand("Second Login", "second.test")
        fake = self.root / "fake-bin"
        fake.mkdir()
        script = """#!/usr/bin/env python3
import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
if name == "ssh":
    print("main.js" if sys.argv[-1].endswith("web-asset") else os.environ["FAKE_RELEASE_ID"])
elif name == "scp" and sys.argv[-2].endswith("/host.env"):
    pathlib.Path(sys.argv[-1]).write_text(pathlib.Path(os.environ["FAKE_HOST_ENV"]).read_text())
elif name == "curl":
    url=sys.argv[-1]
    with open(os.environ["FAKE_URL_LOG"],"a") as log: log.write(url+"\\n")
    if "openid-configuration" in url: print(json.dumps({"issuer":url.split("/.well-known")[0]},separators=(",",":")))
    elif url.endswith("/admin/"): print("404")
    elif url.endswith("/panel"): print("302 /login")
    else: print('{"message":"pong"}')
"""
        for name in ("ssh", "scp", "curl"):
            path = fake / name
            path.write_text(script)
            path.chmod(0o755)
        for kind in ("backend", "web"):
            with self.subTest(kind=kind):
                components = (
                    {
                        name: {"image": "example.invalid/test@sha256:" + "b" * 64}
                        for name in release.REQUIRED["backend"]
                    }
                    if kind == "backend"
                    else {
                        "panel": {
                            "file": "atonota-web-aaaaaaaaaaaa.tar.gz",
                            "sha256": "c" * 64,
                        }
                    }
                )
                manifest = release.new_manifest(kind, "a" * 40, 1, components)
                # Resume also supplies only the manifest, without a local deploy archive.
                folder = self.root / f"health-{kind}"
                folder.mkdir()
                (folder / "release.json").write_text(json.dumps(manifest))
                if kind == "web":
                    shutil.copytree(packed, folder / "deploy")
                log = self.root / f"urls-{kind}"
                result = subprocess.run(
                    [str(self.source / "bin/health"), "alpha", str(folder)],
                    env={
                        **os.environ,
                        "PATH": f"{fake}:{os.environ['PATH']}",
                        "FAKE_RELEASE_ID": manifest["release_id"],
                        "FAKE_URL_LOG": str(log),
                        "FAKE_HOST_ENV": str(packed / "environments/alpha.env"),
                    },
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                urls = log.read_text().splitlines()
                self.assertTrue(urls)
                self.assertTrue(
                    all(".alpha.example.test/" in url for url in urls), urls
                )


if __name__ == "__main__":
    unittest.main()
