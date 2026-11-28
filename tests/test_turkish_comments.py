"""Tests for scripts/turkish_comments.py, the Turkish code comment counter.

Run: python3 -I -m unittest discover -s tests -p test_turkish_comments.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import turkish_comments as tc  # noqa: E402


def turkish(path, source):
    """Return the Turkish comments that the counter finds in one source text."""
    return [c for c in tc.comments_in(path, source) if tc.is_turkish(c.text)]


class LanguageScanners(unittest.TestCase):
    def test_python_comment_and_docstring_count_but_strings_do_not(self):
        source = (
            "#!/usr/bin/env python3\n"
            '"""Modül açıklaması."""\n'
            "x = 'Türkçe dizgi'  # satır sonu yorumu\n"
            "y = f'çağrı {x}'\n"
            "def f():\n"
            '    """İşlev açıklaması."""\n'
            "    return \"# değil yorum\"\n"
            "# English only\n"
        )
        found = turkish("a.py", source)
        self.assertEqual([(c.line, c.kind) for c in found], [(2, "docstring"), (3, "comment"), (6, "docstring")])

    def test_typescript_comments_count_but_strings_regex_and_templates_do_not(self):
        source = (
            "// satır yorumu\n"
            "const a = 'çok // değil';\n"
            'const b = "şu /* değil */";\n'
            "const c = `ışık ${a /* gömülü yorum */} // değil`;\n"
            "const r = /https?:\\/\\/ğ/.test(a); // regex sonrası yorum\n"
            "/* blok\n   yorum ü */\n"
            "const d = a / 2 / 3; // bölme sonrası İ\n"
        )
        found = turkish("a.ts", source)
        self.assertEqual([c.line for c in found], [1, 4, 5, 6, 8])

    def test_tsx_text_with_apostrophe_does_not_hide_later_comments(self):
        source = (
            "export function A() {\n"
            "  return (\n"
            "    <p title=\"başlık\">Ayşe'nin {/* jsx yorumu ç */} metni</p>\n"
            "  );\n"
            "}\n"
            "// sonraki yorum ğ\n"
            "const x = y < z ? 'ö' : 'ü';\n"
        )
        found = turkish("a.tsx", source)
        self.assertEqual([c.line for c in found], [3, 6])

    def test_astro_frontmatter_template_script_and_style(self):
        source = (
            "---\n"
            "// ön bölüm yorumu\n"
            "const t = 'Gösterilen metin';\n"
            "---\n"
            "<!-- şablon yorumu -->\n"
            "<p>Ayşe'nin metni {/* ifade yorumu ş */}</p>\n"
            "<br>\n"
            "<script>\n"
            "  // betik yorumu ı\n"
            "  const s = 'çıktı';\n"
            "</script>\n"
            "<style>\n"
            "  /* stil yorumu ü */ a { content: 'ç'; }\n"
            "</style>\n"
        )
        found = turkish("a.astro", source)
        self.assertEqual([c.line for c in found], [2, 5, 6, 9, 13])

    def test_css_has_only_block_comments(self):
        source = "a { background: url(//x/ç.png); }\n/* yorum ç */\nb { content: '/* ş */'; }\n"
        self.assertEqual([c.line for c in turkish("a.css", source)], [2])

    def test_java_comments_count_but_strings_do_not(self):
        source = 'class A {\n  // yorum ç\n  String s = "// ş";\n  /** belge ğ */\n  char c = \'ü\';\n}\n'
        self.assertEqual([c.line for c in turkish("A.java", source)], [2, 4])

    def test_hash_languages(self):
        yaml = "# yorum ç\nkey: 'değer # değil'\nother: x # satır sonu ş\nurl: a#b\n"
        self.assertEqual([c.line for c in turkish("a.yaml", yaml)], [1, 3])
        shell = "#!/bin/sh\n# yorum ğ\necho \"# değil ü\"\necho ${#ö}\n"
        self.assertEqual([c.line for c in turkish("bin/tool", shell)], [2])
        docker = "# yorum ı\nRUN echo ş # bu da yorum değil satır başı değil\n"
        self.assertEqual([c.line for c in turkish("Dockerfile", docker)], [1])

    def test_freemarker_and_html_comments(self):
        ftl = "<#-- şablon yorumu -->\n<p>${msg('çıkış')}</p>\n<!-- html yorumu ğ -->\n"
        self.assertEqual([c.line for c in turkish("a.ftl", ftl)], [1, 3])
        html = "{# jinja yorumu ç #}\n<p>Görünen metin</p>\n<script>// betik ş\n</script>\n"
        self.assertEqual([c.line for c in turkish("a.html", html)], [1, 3])

    def test_translation_catalogue_and_data_files_are_not_scanned(self):
        self.assertEqual(tc.classify("x/messages_tr.properties"), "data")
        self.assertEqual(tc.classify("x/translations/tr.csv"), "data")
        self.assertEqual(tc.classify("x/notes.md"), "data")
        self.assertEqual(tc.classify("x/messages_en.properties"), "hash-line")


class Gate(unittest.TestCase):
    def test_count_above_baseline_fails_and_names_the_folder(self):
        baseline = {"folders": {"src": 2, "tests": 0}}
        problems = tc.compare({"src": 3, "tests": 0}, baseline)
        self.assertEqual(len(problems), 1)
        self.assertIn("src", problems[0])

    def test_count_at_or_below_baseline_passes(self):
        baseline = {"folders": {"src": 2, "tests": 1}}
        self.assertEqual(tc.compare({"src": 2, "tests": 0}, baseline), [])

    def test_new_turkish_comment_in_a_copied_file_fails_the_gate(self):
        """Example from the acceptance criteria: add one Turkish comment to a real file."""
        real = ROOT / "scripts" / "find-overflow.mjs"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "scripts" / "find-overflow.mjs"
            target.parent.mkdir()
            shutil.copyfile(real, target)
            before = tc.count_by_folder(tc.scan(Path(tmp), ["scripts/find-overflow.mjs"]))
            baseline = {"folders": dict(before)}
            self.assertEqual(tc.compare(before, baseline), [])
            with target.open("a", encoding="utf-8") as handle:
                handle.write("// Yeni bir Türkçe yorum\n")
            after = tc.count_by_folder(tc.scan(Path(tmp), ["scripts/find-overflow.mjs"]))
            self.assertEqual(after["scripts"], before.get("scripts", 0) + 1)
            self.assertNotEqual(tc.compare(after, baseline), [])


class Repository(unittest.TestCase):
    """The real gate: today's repository must not exceed the baseline."""

    @classmethod
    def setUpClass(cls):
        cls.files = tc.tracked_files(ROOT)
        cls.result = tc.scan(ROOT, cls.files)

    def test_every_tracked_file_in_scope_has_a_known_type(self):
        unknown = [path for path in self.files if tc.classify(path) == "unknown"]
        self.assertEqual(unknown, [], "add these file types to scripts/turkish_comments.py")

    def test_every_code_file_scans_without_error(self):
        self.assertEqual(self.result.errors, [])

    def test_count_does_not_exceed_baseline(self):
        baseline = json.loads(tc.BASELINE.read_text(encoding="utf-8"))
        problems = tc.compare(tc.count_by_folder(self.result), baseline)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_baseline_covers_every_scope_folder(self):
        baseline = json.loads(tc.BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(sorted(baseline["folders"]), sorted(tc.SCOPE))

    def test_cli_prints_count_by_folder_and_check_passes(self):
        run = subprocess.run(
            [sys.executable, "-I", str(ROOT / "scripts" / "turkish_comments.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        for folder in tc.SCOPE:
            self.assertIn(folder + "/", run.stdout)


if __name__ == "__main__":
    unittest.main()
