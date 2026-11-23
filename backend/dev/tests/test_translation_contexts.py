"""GILT step 5c: contracts name the translation contexts the code really uses."""

import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
IDENTITY_CONTRACT = BACKEND / "contracts" / "platform_core-identity.openapi.yaml"
IDENTITY_CSV = BACKEND / "apps" / "platform_core" / "platform_core" / "translations" / "tr.csv"
IDENTITY_SOURCE = BACKEND / "apps" / "platform_core" / "platform_core" / "www" / "login.py"


class IdentityContractContextTests(unittest.TestCase):
    def test_contract_context_matches_code_and_catalog(self):
        contract = IDENTITY_CONTRACT.read_text(encoding="utf-8")
        named = set(re.findall(r"with the context `([^`]+)`", contract))
        self.assertEqual(named, {"platform_core.identity"})
        self.assertIn('context="platform_core.identity"', IDENTITY_SOURCE.read_text(encoding="utf-8"))
        self.assertIn(",platform_core.identity\n", IDENTITY_CSV.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
