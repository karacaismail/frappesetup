"""Product and license boundary tests (G-157, decision 5).

AtonotA Login code is MIT. Keycloak and the bundled extensions are Apache-2.0. The two licenses
stay in separate files.
"""

import re
import unittest
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1]
KEYCLOAK = PRODUCT.parent / "keycloak"
BRAND = "AtonotA Login"


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

    def test_brand_name_is_written_exactly(self):
        for path in [PRODUCT / "README.md", PRODUCT / "THIRD-PARTY-NOTICES.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(BRAND, text, path.name)
            self.assertIsNone(re.search(r"\b(?!AtonotA Login)[Aa][Tt][Oo][Nn][Oo][Tt][Aa] [Ll]ogin\b", text), path.name)

    def test_visible_brand_comes_from_the_realm_display_name(self):
        example = (KEYCLOAK / ".env.example").read_text(encoding="utf-8")
        production = (KEYCLOAK / "production.env.example").read_text(encoding="utf-8")
        for text in (example, production):
            # AJA-1062: the value comes from PRODUCT_NAME in backend/brand.env; examples hold a placeholder.
            self.assertRegex(text, r"(?m)^IDENTITY_BRAND_NAME=<PRODUCT_NAME>$")


if __name__ == "__main__":
    unittest.main()
