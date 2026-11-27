"""Check which identity-sync origin the preview writes before starting Frappe."""

import json
import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class SiteSeedTest(unittest.TestCase):
    def test_full_browser_preview_preserves_https_revocation_origin(self):
        source = Path(__file__).resolve().parents[1] / "preview/site-seed.py"
        frappe = Mock()
        frappe.init.side_effect = StopIteration
        settings = {
            "PANE_PORT": "43820",
            "PRODUCT_NAME": runpy.run_path(
                str(source.parents[2] / "deploy/brand.py")
            )["load_brand"]()["PRODUCT_NAME"],
            "E2E_LIFECYCLE_IDENTITIES": "{}",
            "E2E_FULL_BROWSER_FIXTURES": "1",
            "E2E_KEYCLOAK_CLIENT_SECRET": "synthetic-secret",
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
        config = json.loads(write.call_args.args[0])
        self.assertEqual(config["keycloak_internal_url"], "https://identity-sync:9444")
        self.assertEqual(config["mobile_identity_sync_url"], "https://identity-sync:9443")
