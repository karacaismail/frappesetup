"""Exercise the translation checks through the readiness command."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).with_name("gate.py").resolve()
SCRATCH = GATE.parents[3] / ".pane" / "scratch"
TR = "apps/sample_app/sample_app/translations/tr.csv"
CORE = "apps/frappe/frappe"


class TranslationChecksTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH if SCRATCH.is_dir() else None)
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name)
        subprocess.run(["git", "init", "--quiet", self.repository], check=True)
        self.root = self.repository / "backend"

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def scan(self, *args, structured=True):
        return subprocess.run(
            [sys.executable, "-B", GATE, "--root", self.root, *(["--json"] if structured else []), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_every_app_translation_record_requires_three_columns(self):
        self.write(
            TR, '"Save, now","Save translation",\nTwo,Two translation\nFour,Four translation,,extra\n\n'
        )
        other = "apps/second_app/second_app/translations/es.csv"
        self.write(other, "One,Translation\n")
        self.write("apps/sample_app/sample_app/fixtures/example.csv", "Ignore,me\n")
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stdout)
        findings = json.loads(result.stdout)["findings"]
        self.assertCountEqual(
            [(row["path"], row["line"], row["rule"]) for row in findings],
            [(TR, line, "translation-columns") for line in (2, 3, 4)] + [(other, 1, "translation-columns")],
        )

    def test_source_and_context_pair_is_unique_per_file(self):
        self.write(TR, '"Save\nnow","First",menu\n"Save\\nnow",Second,menu\n"Save\nnow",Third,dialog\n')
        self.write(TR.replace("tr.csv", "es.csv"), '"Save\nnow",Fourth,menu\n')
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stdout)
        findings = json.loads(result.stdout)["findings"]
        self.assertEqual(
            [(row["path"], row["line"], row["rule"]) for row in findings], [(TR, 3, "translation-duplicate")]
        )
        self.assertIn("line 1", findings[0]["message"])

    def test_contextless_source_matches_core_csv_and_po_in_the_same_language(self):
        self.write(TR, 'Open,Aç,\nOpen,Aç,button\n"Save\nnow",Kaydet,\nOld,Eski,\nSpanish,İspanyolca,\n')
        self.write(f"{CORE}/translations/tr.csv", "Open,Çekirdek\n")
        self.write(
            f"{CORE}/locale/tr.po",
            'msgid ""\nmsgstr ""\n\nmsgctxt "action"\nmsgid ""\n"Save\\n"\n"now"\nmsgstr "Kaydet"\n'
            '#~ msgid "Old"\n#~ msgstr "Eski"\n',
        )
        self.write(f"{CORE}/locale/es.po", 'msgid "Spanish"\nmsgstr "Español"\n')
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["translation_core"], "fail")
        self.assertEqual(
            [(row["path"], row["line"], row["rule"]) for row in payload["findings"]],
            [(TR, 1, "translation-core"), (TR, 3, "translation-core")],
        )

    def test_valid_contextual_translation_allows_shared_core_source(self):
        self.write(TR, '"He said ""open""",Aç,menu\nOpen,Aç,button\n')
        self.write(f"{CORE}/locale/tr.po", 'msgid "Open"\nmsgstr "Aç"\n')
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["checks"]["translation_core"], "pass")

    def test_malformed_csv_reports_the_record_start(self):
        self.write(TR, 'Open,Aç,\n"Broken\nrecord,Çeviri,dialog\n')
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stdout)
        findings = json.loads(result.stdout)["findings"]
        self.assertEqual(
            [(row["path"], row["line"], row["rule"]) for row in findings], [(TR, 2, "translation-columns")]
        )

    def test_missing_core_catalog_is_reported_without_failing(self):
        self.write(TR, "Open,Aç,\n")
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["checks"]["translation_core"], "not_run")
        self.assertIn("translation_core: not_run", self.scan(structured=False).stderr)

    def test_explicit_core_checkout_supports_parent_locale(self):
        locale = TR.replace("tr.csv", "tr-TR.csv")
        self.write(locale, "Open,Aç,\n")
        self.write("separate/frappe/locale/tr.po", 'msgid "Open"\nmsgstr "Aç"\n')
        result = self.scan("--frappe-root", str(self.root / "separate"))
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["checks"]["translation_core"], "fail")
        [(path, rule)] = [(row["path"], row["rule"]) for row in payload["findings"]]
        self.assertEqual((path, rule), (locale, "translation-core"))
