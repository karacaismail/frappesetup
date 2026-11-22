"""Keep shell identity constraints explicit in the shared contract."""

import unittest
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts.md"


class ShellIdentityContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = CONTRACT.read_text(encoding="utf-8")

    def test_shell_requires_nonblank_installation_and_sid(self):
        identity = self.contract.split("### Telefon kimliği\n", 1)[1].split("\n### ", 1)[0]
        self.assertIn("Kabuk, `installation` ve `sid` alanlarında boş olmayan metin ister.", identity)

    def test_document_methods_have_document_permissions(self):
        allowlist = self.contract.split("### Website User için yöntem izin listesi\n", 1)[1]
        self.assertIn("`/api/v2/document/<doctype>/<name>/method/<method>/` yolu", allowlist)
        self.assertIn("`run_method` biçimi yöntem izin listesinin dışındadır.", allowlist)
        self.assertIn("Frappe bu çağrılarda belge izinlerini denetler.", allowlist)
