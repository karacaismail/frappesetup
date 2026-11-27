"""Brand settings reach local fixtures without starting any service (AJA-1248)."""

import json
import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
LOAD_BRAND = runpy.run_path(str(BACKEND / "deploy/brand.py"))["load_brand"]
FILES = (
    "docs/dagitim/ortamlar.md",
    "contracts/platform_core-identity.openapi.yaml",
    "docs/contracts.md",
    "dev/tests/test_login_method_allowlists.py",
    "e2e/tests/test_stack_tenant.py",
    "e2e/tests/test_stack_preview_seed.py",
    "e2e/tests/test_login_providers_http.py",
    "e2e/stack",
    "e2e/preview/site-seed.py",
    "e2e/preview/fixtures.py",
    "e2e/browser.spec.ts",
    "docs/dagitim/press-imaji.md",
    "dev/tests/test_login_reads_access.py",
    "dev/tests/test_e2e_stack.py",
)


class BrandSettingsTest(unittest.TestCase):
    def test_preview_passes_shared_product_name_into_the_container(self):
        with patch.dict(sys.modules, {"browser_keycloak": Mock()}):
            seed = runpy.run_path(str(BACKEND / "e2e/preview/fixtures.py"))["seed_site"]
        supplied = {"PRODUCT_NAME": "Stale preview name"}
        with (
            patch.dict(seed.__globals__, {
                "docker_executable": lambda: "/tools/docker",
                "docker_context": lambda: "colima-factory",
            }),
            patch("subprocess.run", return_value=Mock(stdout="{}")) as run,
        ):
            seed("isolated-preview", "tenant-web", "/bench", supplied)
        command = run.call_args.args[0]
        self.assertIn("PRODUCT_NAME", [command[i + 1] for i, arg in enumerate(command) if arg == "--env"])
        self.assertEqual(run.call_args.kwargs["env"]["PRODUCT_NAME"], LOAD_BRAND()["PRODUCT_NAME"])
        self.assertEqual(supplied, {"PRODUCT_NAME": "Stale preview name"})

    def test_stack_setup_uses_shared_brand_over_stale_local_values(self):
        setup = runpy.run_path(str(BACKEND / "e2e/stack"))["setup"]
        with (
            patch.dict(os.environ, {"PANE_PORT": "43820", "IDENTITY_BRAND_NAME": "Old name"}, clear=True),
            patch.dict(setup.__globals__, {
                "default_settings": lambda: {"IDENTITY_BRAND_NAME": "Old template"},
                "credentials": lambda path: {"IDENTITY_BRAND_NAME": "Old local file"},
                "assert_ignored": Mock(),
                "require_compose_settings": Mock(),
            }),
        ):
            environment, _, _ = setup()
        self.assertEqual(environment["IDENTITY_BRAND_NAME"], LOAD_BRAND()["PRODUCT_NAME"])

    def test_assigned_files_do_not_repeat_public_brand_values(self):
        scanner = runpy.run_path(str(BACKEND / "deploy/tests/test_brand_hardcode.py"))
        for name in FILES:
            with self.subTest(file=name):
                hits = scanner["find_hits"](ROOT, ["backend/" + name], LOAD_BRAND(), [])
                self.assertEqual(hits, [])

    def test_tenant_login_uses_the_configured_product_name(self):
        settings = runpy.run_path(str(BACKEND / "e2e/stack"))["tenant_login_settings"]
        environment = {
            "KC_PUBLIC_URL": "http://identity.localhost:43820",
            "ATONOTA_SITE_TENANT1_URL": "http://tenant1.localhost:43821",
            "ATONOTA_SITE_TENANT1_SECRET": "synthetic-client",
            "IDENTITY_BRAND_NAME": "Ornek [Giris] + Hesap",
        }
        self.assertEqual(
            settings(environment)["identity_brand_name"], environment["IDENTITY_BRAND_NAME"]
        )

    def test_preview_seed_uses_the_injected_product_name(self):
        source = BACKEND / "e2e/preview/site-seed.py"
        frappe = Mock()
        frappe.init.side_effect = StopIteration
        settings = {
            "PANE_PORT": "43820",
            "PRODUCT_NAME": "Ornek [Giris] + Hesap",
            "E2E_LIFECYCLE_IDENTITIES": "{}",
            "E2E_FULL_BROWSER_FIXTURES": "0",
            "E2E_KEYCLOAK_CLIENT_SECRET": "synthetic-client",
            "E2E_PROVIDER_IP": "192.0.2.1",
            "E2E_PREVIEW_SYNC_ORIGIN": "http://identity-sync.localhost:43825",
        }
        with (
            patch.dict(sys.modules, {"frappe": frappe}),
            patch.dict(os.environ, settings, clear=True),
            patch.object(sys, "argv", [str(source), "tenant-web"]),
            patch.object(os, "chdir"),
            patch.object(Path, "read_text", return_value="{}"),
            patch.object(Path, "write_text") as write,
            self.assertRaises(StopIteration),
        ):
            runpy.run_path(str(source), run_name="__main__")
        self.assertEqual(json.loads(write.call_args.args[0])["identity_brand_name"], settings["PRODUCT_NAME"])
