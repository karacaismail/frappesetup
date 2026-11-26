"""Product and license boundary tests (G-157, decision 5).

The `atonota_login` product code is MIT. Keycloak and the bundled extensions are Apache-2.0. The two licenses
stay in separate files.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.brand_values import PRODUCT_NAME

PRODUCT = Path(__file__).resolve().parents[1]
KEYCLOAK = PRODUCT.parent / "keycloak"
# The examples may hold the brand.env value or the placeholder (AJA-1059 plan, section 2).


class ProductBoundaryTest(unittest.TestCase):
    def test_product_folder_carries_the_mit_license(self):
        text = (PRODUCT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("MIT License"))
        self.assertNotIn("Apache", text)

    def test_third_party_notice_lists_apache_parts_apart(self):
        text = (PRODUCT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Apache-2.0", text)
        dockerfile = (KEYCLOAK / "Dockerfile").read_text(encoding="utf-8")
        version = re.search(r"(?m)^ARG KEYCLOAK_VERSION=(\S+)$", dockerfile).group(1)
        self.assertIn(f"Keycloak {version}", text)
        for part in ("keycloak-magic-link", "apple-identity-provider-keycloak", "keycloak-webhook-listener"):
            self.assertIn(part, text)
        self.assertNotIn("MIT License", text)

    def test_the_apache_fork_keeps_its_own_license(self):
        text = (KEYCLOAK / "event-listener" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Apache License", text)

    def test_python_files_name_the_product_license(self):
        for path in sorted((PRODUCT / "atonota_login").glob("*.py")) + [PRODUCT / "bin" / "atonota-login"]:
            head = path.read_text(encoding="utf-8")[:400]
            self.assertIn("SPDX-License-Identifier: MIT", head, path.name)

    def test_documents_point_to_the_brand_setting(self):
        # AJA-1061: the documents name no brand. They point to backend/brand.env instead.
        for path in [PRODUCT / "README.md", PRODUCT / "THIRD-PARTY-NOTICES.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(PRODUCT_NAME.lower(), text.lower(), path.name)
            self.assertIn("backend/brand.env", text, path.name)

    def test_visible_brand_comes_from_the_realm_display_name(self):
        example = (KEYCLOAK / ".env.example").read_text(encoding="utf-8")
        production = (KEYCLOAK / "production.env.example").read_text(encoding="utf-8")
        for text in (example, production):
            # AJA-1062: the value comes from PRODUCT_NAME in backend/brand.env; examples hold a placeholder.
            self.assertRegex(text, r"(?m)^IDENTITY_BRAND_NAME=<PRODUCT_NAME>$")


class CommandBrandTest(unittest.TestCase):
    """AJA-1061: the command help takes the product name from the PRODUCT_NAME value."""

    @classmethod
    def setUpClass(cls):
        path = PRODUCT / "bin" / "atonota-login"
        loader = importlib.machinery.SourceFileLoader("atonota_login_brand_command", str(path))
        spec = importlib.util.spec_from_loader("atonota_login_brand_command", loader)
        cls.command = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.command)

    def help_text(self, environment):
        output = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=False), contextlib.redirect_stdout(output):
            if "PRODUCT_NAME" not in environment:
                os.environ.pop("PRODUCT_NAME", None)
            with self.assertRaises(SystemExit):
                self.command.main(["--help"])
        return output.getvalue()

    def test_help_names_the_product_from_the_environment(self):
        for brand in ("Deneme Marka", "Ikinci Marka"):
            with self.subTest(brand=brand):
                self.assertIn(f"{brand} platform tools", self.help_text({"PRODUCT_NAME": brand}))

    def test_help_uses_the_technical_name_without_the_value(self):
        text = self.help_text({})
        self.assertIn("atonota_login platform tools", text)
        self.assertNotIn(PRODUCT_NAME.lower(), text.lower())

if __name__ == "__main__":
    unittest.main()
