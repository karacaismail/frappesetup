"""Regression tests for the repository rename command."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NAMING = Path(__file__).resolve().parents[1]


class RenameTests(unittest.TestCase):
    def setUp(self):
        scratch = NAMING.parents[2] / ".pane/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)
        self.root = self.workspace / "repo"
        self.root.mkdir()
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            text=True,
            capture_output=True,
            check=True,
        ).stdout

    def write(self, filename, content):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def rename(self, entries, *options):
        mapping = NAMING / "rename-map.json"
        if entries is not None:
            mapping = self.workspace / "rename-map.json"
            mapping.write_text(json.dumps(entries), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(NAMING / "apply_renames.py"),
                "--repo",
                str(self.root),
                "--map",
                str(mapping),
                *options,
            ],
            capture_output=True,
            text=True,
        )

    def test_real_map_renames_module_gate_literals(self):
        paths = {
            "backend/dev/ai_readiness/gate.py": ('module == "yapay_zeka"\n', 'module == "ai"\n'),
            "backend/apps/press_tr/tests/test_module_boundaries.py": (
                'layer = APP / "kimlik"\n',
                'layer = APP / "press_identity"\n',
            ),
        }
        for path, (source, _) in paths.items():
            self.write(path, source)
        self.git("add", ".")
        self.assertEqual(self.rename(None, "--check-modules").returncode, 1)
        result = self.rename(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, (_, expected) in paths.items():
            self.assertEqual((self.root / path).read_text(), expected)
        self.assertEqual(self.rename(None, "--check-modules").returncode, 0)

    def test_real_map_preserves_fstring_copy_and_renames_expressions(self):
        errors = "backend/libs/oidc_verify/src/oidc_verify"
        keycloak = "backend/identity/keycloak/tests"
        self.write(
            f"{errors}/hatalar.py",
            'def reject(code):\n    raise ValueError(f"Bilinmeyen hata kodu: {code}")\n',
        )
        self.write(
            f"{keycloak}/yardimci.py",
            'def ortam(ad):\n    raise KeyError(f"{ad} ortam değişkeni boş. '
            'Testi bin/kc-dev.sh test ile çalıştırın.")\n'
            'def request(belirtec):\n    return f"Bearer {belirtec}"\n',
        )
        self.git("add", ".")
        outcome = self.rename(None)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertIn('f"Bilinmeyen hata kodu: {code}"', (self.root / errors / "errors.py").read_text())
        rewritten = (self.root / keycloak / "helpers.py").read_text()
        self.assertIn('f"{name} ortam değişkeni boş. Testi bin/kc-dev.sh test ile çalıştırın."', rewritten)
        self.assertIn('f"Bearer {token}"', rewritten)

    def test_real_map_finds_unscoped_module_literals_and_raw_embedded_imports(self):
        ref = self.write(
            "backend/apps/platform_core/platform_core/erisim/tests/test_translations.py",
            'layer = ROOT / "erisim"\nasset = "/assets/platform_core/kimlik/logo.svg"\n',
        )
        self.write("backend/dev/unlisted.py", 'snippet = "from platform_core.kimlik.api import x"\n')
        self.git("add", ".")
        outcome = self.rename(None, "--check-modules")
        self.assertEqual(outcome.returncode, 1, outcome.stdout)
        self.assertIn("backend/dev/unlisted.py:1", outcome.stdout)
        outcome = self.rename(None)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertFalse(ref.exists())
        target = self.root / "backend/apps/platform_core/platform_core/access/tests/test_translations.py"
        self.assertIn('ROOT / "access"', target.read_text())

    def test_redirect_is_restored_if_interrupted_after_git_mv(self):
        self.write("backend/PROJE-KAYDI.md", "Record\n")
        self.git("add", ".")
        self.git("mv", "backend/PROJE-KAYDI.md", "backend/PROJECT-RECORD.md")
        rules = [{"old": "backend/PROJE-KAYDI.md", "new": "backend/PROJECT-RECORD.md", "type": "path"}]
        outcome = self.rename(rules)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertIn("PROJECT-RECORD.md", (self.root / "backend/PROJE-KAYDI.md").read_text())

    def test_module_allowlist_accepts_only_exact_file_and_line(self):
        note = '# Keep the legacy example "platform_core.kimlik".\n'
        source = self.write("backend/example.py", note)
        self.git("add", ".")
        allowlist = self.workspace / "allowed.json"
        allowlist.write_text(json.dumps([{"path": "backend/example.py", "line_text": note.strip()}]))
        flags = ("--check-modules", "--module-allowlist", str(allowlist))
        self.assertEqual(self.rename(None, *flags).returncode, 0)
        source.write_text(note + 'example = "platform_core.kimlik"\n')
        report = self.rename(None, *flags)
        self.assertEqual(report.returncode, 1)
        self.assertIn("backend/example.py:2", report.stdout)

    def test_reports_markdown_code_and_links_without_mutating_content(self):
        content = "Kimlik hakkında. `platform_core.kimlik`. [Görev](docs/isler/kimlik-realm.md).\n"
        source = self.write("backend/README.md", content)
        self.git("add", ".")
        report = self.rename(None, "--report-docs")
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertIn("backend/README.md:1: platform_core.kimlik", report.stdout)
        self.assertIn("kimlik-realm.md", report.stdout)
        self.assertEqual(source.read_text(), content)

    def test_module_allowlist_covers_english_ai_copy(self):
        self.write(
            "backend/apps/platform_core/platform_core/api/ai.py",
            '"""Endpoints of the AI access layer. The business rules live in the '
            '`platform_core.yapay_zeka` module.\n"""\n',
        )
        self.write(
            "backend/contracts/platform_core-ai.openapi.yaml",
            "description: |\n"
            "  This contract describes the endpoints of the `platform_core.yapay_zeka` module.\n",
        )
        self.git("add", ".")
        result = self.rename(None, "--check-modules")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_mobile_client_inline_module_reference_is_renamed(self):
        path = "backend/identity/identity_sync/tests/test_mobile_client.py"
        original = (
            '"""The client lives in another job\'s folder '
            "(`apps/platform_core/.../mobil/identity_sync_client.py`).\n"
            'This sentence keeps its mobil wording.\n"""\n'
            'client = ROOT / "mobil" / "identity_sync_client.py"\n'
        )
        source = self.write(path, original)
        unrelated = self.write(
            "backend/unrelated.py", '"""See `apps/platform_core/.../mobil/identity_sync_client.py`. """\n'
        )
        self.git("add", ".")
        baseline = self.rename(None, "--check-modules")
        self.assertIn(f"{path}:1: mobil", baseline.stdout)
        renamed = self.rename(None)
        self.assertEqual(renamed.returncode, 0, renamed.stderr)
        self.assertIn("`apps/platform_core/.../mobile/identity_sync_client.py`", source.read_text())
        self.assertIn('ROOT / "mobile" / "identity_sync_client.py"', source.read_text())
        self.assertIn("This sentence keeps its mobil wording.", source.read_text())
        self.assertIn("/mobil/", unrelated.read_text())
        check = self.rename(None, "--check-modules")
        self.assertNotIn(path, check.stdout)
        self.assertIn("backend/unrelated.py", check.stdout)

    def test_non_utf8_source_stops_before_any_changes(self):
        source = self.write("backend/sample.txt", "legacy\n")
        invalid = self.write("backend/unreadable.txt", "")
        invalid.write_bytes(b"legacy\xff\n")
        self.git("add", ".")
        rules = [{"old": "legacy", "new": "updated", "type": "identifier"}]
        result = self.rename(rules)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend/unreadable.txt", result.stderr)
        self.assertEqual(source.read_text(), "legacy\n")
        self.assertEqual(invalid.read_bytes(), b"legacy\xff\n")

    def test_real_map_uses_specific_keycloak_test_names(self):
        source = self.write("backend/identity/keycloak/tests/example.py", "deger = 'x'\nveri = {}\n")
        self.git("add", ".")
        outcome = self.rename(None)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(source.read_text(), "environment_value = 'x'\nrequest_body = {}\n")

    def test_email_diagnostics_name_the_current_settings(self):
        base = "backend/identity/keycloak/themes/atonota/test/tests"
        self.write(
            f"{base}/eposta.spec.ts",
            "const magicKc = process.env.SIHIRLI_KC_URL;\n"
            "test.skip(!magicKc, 'Eklentili Keycloak adresi (SIHIRLI_KC_URL) verilmedi. "
            "Tema deneme ortamında eklenti yok.');\n"
            "const token = process.env.SIHIRLI_ADMIN_TOKEN;\n"
            "if (!token) throw new Error('SIHIRLI_ADMIN_TOKEN gerekli');\n",
        )
        self.git("add", ".")
        result = self.rename(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = (self.root / base / "email.spec.ts").read_text()
        self.assertEqual(output.count("KC_MAGIC_LINK_URL"), 2)
        self.assertEqual(output.count("KC_MAGIC_LINK_ADMIN_TOKEN"), 2)
        self.assertNotIn("SIHIRLI_", output)

    def test_real_map_distinguishes_email_properties_slugs_and_copy(self):
        directory = "backend/identity/keycloak/themes/atonota/test/tests"
        pattern = "const pattern = /https?:\\/\\/[^\\s\"'<>]+/g;\n"
        self.write(
            f"{directory}/eposta.spec.ts",
            "const copy = { parola: { title: 'Yeni parola oluşturun' }, islem: {} };\n"
            + pattern
            + "const slug = 'parola';\n"
            + "expect(copy.parola.title).toBe('Yeni parola oluşturun');\n",
        )
        self.git("add", ".")
        result = self.rename(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / directory / "email.spec.ts"
        self.assertEqual(
            target.read_text(),
            "const copy = { 'password-reset': { title: 'Yeni parola oluşturun' }, 'required-actions': {} };\n"
            + pattern
            + "const slug = 'password-reset';\n"
            + "expect(copy['password-reset'].title).toBe('Yeni parola oluşturun');\n",
        )

    def test_preserves_copy_and_changes_only_translation_source_keys(self):
        script = self.write(
            "backend/app/feature.py",
            'ad = "Dağıtım adı"  # ad değişkeni\nkind = "AI Provider"\nmessage = "AI Provider kaydı"\n',
        )
        document = self.write("backend/PROJE-KAYDI.md", "AI Provider adı bu kayıtta kalır.\n")
        metadata = self.write("backend/app/record.json", '{"name":"AI Provider","label":"AI Provider"}\n')
        csv_path = self.write(
            "backend/app/translations/tr.csv", 'AI Provider,"AI Provider, sağlayıcı",AI Provider\n'
        )
        po_path = self.write(
            "backend/app/locale/tr.po", 'msgid ""\n"AI "\n"Provider"\nmsgstr "AI Provider sağlayıcı"\n'
        )
        self.git("add", ".")
        entries = [
            {"old": "ad", "new": "name", "type": "identifier"},
            {"old": "AI Provider", "new": "PLT AI Provider", "type": "doctype"},
            {"old": "backend/PROJE-KAYDI.md", "new": "backend/PROJECT-RECORD.md", "type": "path"},
        ]
        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            script.read_text(),
            'name = "Dağıtım adı"  # ad değişkeni\nkind = "PLT AI Provider"\nmessage = "AI Provider kaydı"\n',
        )
        self.assertEqual(
            (document.parent / "PROJECT-RECORD.md").read_text(), "AI Provider adı bu kayıtta kalır.\n"
        )
        self.assertEqual(document.read_text(), "[Yeni dosyayı açın.](PROJECT-RECORD.md)\n")
        self.assertEqual(metadata.read_text(), '{"name":"PLT AI Provider","label":"AI Provider"}\n')
        self.assertEqual(csv_path.read_text(), 'PLT AI Provider,"AI Provider, sağlayıcı",PLT AI Provider\n')
        self.assertEqual(po_path.read_text(), 'msgid "PLT AI Provider"\nmsgstr "AI Provider sağlayıcı"\n')
        self.assertIn("0 tracked file(s)", self.rename(entries, "--dry-run").stdout)

    def test_rejects_a_python_binding_collision(self):
        source = self.write(
            "backend/app/feature.py", "def some_function(name):\n    ad = name\n    return ad\n"
        )
        self.git("add", ".")
        result = self.rename([{"old": "ad", "new": "name", "type": "identifier"}])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Name collision", result.stderr)
        self.assertIn("ad = name", source.read_text())

    def test_translation_rename_cannot_merge_two_sources_in_one_context(self):
        source = self.write("backend/app/record.json", '{"name":"Old Label"}\n')
        translations = self.write(
            "backend/app/translations/tr.csv",
            "Old Label,Eski çeviri,Shared context\nNew Label,Yeni çeviri,Shared context\n",
        )
        before = translations.read_bytes()
        self.git("add", ".")
        rules = [{"old": "Old Label", "new": "New Label", "type": "doctype"}]
        result = self.rename(rules)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("backend/app/translations/tr.csv:2", result.stderr)
        self.assertEqual(translations.read_bytes(), before)
        self.assertEqual(source.read_text(), '{"name":"Old Label"}\n')

        translations.write_text("Old Label,Eski çeviri,First context\nNew Label,Yeni çeviri,Second context\n")
        result = self.rename(rules)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            translations.read_text(),
            "New Label,Eski çeviri,First context\nNew Label,Yeni çeviri,Second context\n",
        )

    def test_settings_check_only_prints_legacy_keys(self):
        config = self.write("backend/config.env", "export LEGACY_KEY=never-print-this\n")
        self.git("add", ".")
        entries = [{"old": "LEGACY_KEY", "new": "NEW_KEY", "type": "setting"}]
        result = self.rename(entries, "--check-settings", str(config))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("LEGACY_KEY", result.stdout)
        self.assertNotIn("never-print-this", result.stdout)

    def test_preserves_template_copy_html_yaml_and_properties(self):
        template = self.write("backend/view.ts", "const label = `Durum: ${durum}`;\n")
        markup = self.write("backend/view.ftl", '<div class="durum">Son durum</div>\n')
        contract = self.write("backend/contracts/example.yaml", "summary: >-\n  Son durum\n")
        properties = self.write("backend/view.properties", "caption=Son durum\n")
        binary = self.write("backend/sample.bin", "")
        binary.write_bytes(b"\0durum\xff")
        self.git("add", ".")
        entries = [{"old": "durum", "new": "status", "type": "identifier"}]
        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(binary.read_bytes(), b"\0durum\xff")
        self.assertEqual(template.read_text(), "const label = `Durum: ${status}`;\n")
        self.assertEqual(markup.read_text(), '<div class="status">Son durum</div>\n')
        self.assertEqual(contract.read_text(), "summary: >-\n  Son durum\n")
        self.assertEqual(properties.read_text(), "caption=Son durum\n")

    def test_preserves_openapi_copy_after_blank_lines_and_its_translation_key(self):
        content = "First paragraph.\n\nSee `docs/sozlesmeler.md` and `site-kiraci1`.\n"
        contract = self.write(
            "backend/contracts/identity_sync.openapi.yaml",
            "description: |\n  First paragraph.\n\n  See `docs/sozlesmeler.md` and `site-kiraci1`.\n"
            "technical: site-kiraci1\n",
        )
        translation = self.write(
            "backend/identity/identity_sync/translations/tr.csv",
            f'"{content}",Türkçe karşılık,identity_sync.openapi.yaml: info.description\n',
        )
        translation_before = translation.read_bytes()
        self.git("add", ".")
        rules = [
            {"old": "docs/sozlesmeler.md", "new": "docs/contracts.md", "type": "reference"},
            {"old": "site-kiraci1", "new": "site-tenant1", "type": "setting"},
        ]
        result = self.rename(rules)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  See `docs/sozlesmeler.md` and `site-kiraci1`.\n", contract.read_text())
        self.assertIn("technical: site-tenant1\n", contract.read_text())
        self.assertEqual(translation.read_bytes(), translation_before)

    def test_preserves_yaml_block_copy_with_quoted_keys_and_crlf(self):
        for header, ending in (
            ("description: |", "\r\n"),
            ('"description": |', "\n"),
            ("'description': |2- # Copy", "\r\n"),
        ):
            with self.subTest(header=header, ending=ending):
                target = self.write("backend/contracts/example.yaml", "")
                original_copy = ending.join([header, "  First paragraph.", "", "  See old_name."])
                target.write_bytes((original_copy + ending + "technical: old_name" + ending).encode())
                self.git("add", ".")
                result = self.rename([{"old": "old_name", "new": "new_name", "type": "reference"}])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    target.read_bytes(), (original_copy + ending + "technical: new_name" + ending).encode()
                )

    def test_rejects_a_module_binding_collision(self):
        source = self.write("backend/collision.py", "name = 1\nad = 2\n")
        self.git("add", ".")
        result = self.rename([{"old": "ad", "new": "name", "type": "identifier"}])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Name collision", result.stderr)
        self.assertIn("ad = 2", source.read_text())

    def test_prefixed_doctype_and_path_moves_are_repeatable(self):
        original = "backend/app/legacy/ai_provider.json"
        destination = "backend/app/current/plt_ai_provider.json"
        document = self.write(original, '{"name":"AI Provider","table":"tabAI Provider"}\n')
        use = self.write("backend/app/reference.py", 'provider = "AI Provider"\n')
        self.git("add", ".")
        before = self.git("status", "--porcelain")
        index = self.root / ".git/index"
        before_index = index.read_bytes()
        entries = [
            {"old": "backend/app/legacy", "new": "backend/app/current", "type": "path"},
            {"old": original, "new": destination, "type": "path"},
            {"old": "AI Provider", "new": "PLT AI Provider", "type": "doctype"},
            {"old": "tabAI Provider", "new": "tabPLT AI Provider", "type": "reference"},
        ]

        preview = self.rename(entries, "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn(destination, preview.stdout)
        self.assertEqual(index.read_bytes(), before_index)
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertTrue(document.is_file())
        self.assertFalse((self.root / destination).exists())
        self.assertEqual(use.read_text(), 'provider = "AI Provider"\n')

        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(document.exists())
        self.assertEqual(
            json.loads((self.root / destination).read_text()),
            {"name": "PLT AI Provider", "table": "tabPLT AI Provider"},
        )
        self.assertEqual(use.read_text(), 'provider = "PLT AI Provider"\n')
        before_repeat = self.git("status", "--porcelain"), self.git("diff")

        rerun = self.rename(entries)
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual((self.git("status", "--porcelain"), self.git("diff")), before_repeat)

    def test_only_matching_tracked_backend_references_change(self):
        tracked = self.write(
            "backend/app/hooks.py",
            'from app.kimlik import resolve\nidentities = ("kimlik_api", "other_kimlik")\n',
        )
        fixtures = {
            "backend/other/hooks.py": "from app.kimlik import resolve\n",
            "docs/standartlar/guide.md": "`app.kimlik`\n",
            "backend/docs/standartlar/fixture.py": "from app.kimlik import resolve\n",
            "backend/app/translations/tr.csv": "app.kimlik,Identity\n",
            "backend/app/locale/tr.po": 'msgid "app.kimlik"\n',
            "src/docs.md": "`app.kimlik`\n",
        }
        for filename, content in fixtures.items():
            self.write(filename, content)
        self.git("add", ".")
        fixtures["backend/app/untracked.py"] = "from app.kimlik import resolve\n"
        self.write("backend/app/untracked.py", fixtures["backend/app/untracked.py"])
        entries = [
            {"old": "kimlik", "new": "identity", "type": "identifier", "paths": ["backend/app/*"]},
            {
                "old": "app.kimlik",
                "new": "app.identity",
                "type": "reference",
                "paths": ["docs/standartlar/*", "backend/docs/standartlar/*"],
            },
        ]

        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            tracked.read_text(),
            'from app.identity import resolve\nidentities = ("kimlik_api", "other_kimlik")\n',
        )
        for filename, content in fixtures.items():
            with self.subTest(filename=filename):
                self.assertEqual((self.root / filename).read_text(), content)

    def test_collision_fails_before_any_changes(self):
        source = self.write("backend/old.py", "value = 'old'\n")
        destination = self.write("backend/new.py", "value = 'existing'\n")
        unrelated = self.write("backend/unrelated.py", "value = 'old'\n")
        movable = self.write("backend/first.py", "value = 'first'\n")
        self.git("add", ".")
        before = self.git("status", "--porcelain")
        entries = [
            {"old": "backend/first.py", "new": "backend/first_moved.py", "type": "path"},
            {"old": "backend/old.py", "new": "backend/new.py", "type": "path"},
            {"old": "old", "new": "new", "type": "identifier"},
        ]

        for options in [("--dry-run",), ()]:
            with self.subTest(options=options):
                result = self.rename(entries, *options)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("backend/new.py", result.stderr + result.stdout)
                self.assertEqual(self.git("status", "--porcelain"), before)
                self.assertEqual(self.git("diff"), "")
                self.assertTrue(movable.is_file())
                self.assertEqual(source.read_text(), "value = 'old'\n")
                self.assertEqual(destination.read_text(), "value = 'existing'\n")
                self.assertEqual(unrelated.read_text(), "value = 'old'\n")

    def test_tracked_symlink_is_not_read_as_text(self):
        outside = self.workspace / "external.txt"
        outside.write_text("old_name\n", encoding="utf-8")
        link = self.root / "backend/link.txt"
        link.parent.mkdir()
        link.symlink_to(outside)
        self.git("add", ".")

        result = self.rename([{"old": "old_name", "new": "new_name", "type": "identifier"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(outside.read_text(), "old_name\n")

        move = self.rename([{"old": "backend/link.txt", "new": "backend/moved.txt", "type": "path"}])
        self.assertNotEqual(move.returncode, 0, move.stdout)
        self.assertIn("backend/link.txt", move.stderr)
        self.assertTrue(link.is_symlink())

    def test_planned_file_cannot_be_a_destination_directory(self):
        first = self.write("backend/first.py", "")
        second = self.write("backend/second.py", "")
        self.git("add", ".")
        result = self.rename(
            [
                {"old": "backend/first.py", "new": "backend/group", "type": "path"},
                {"old": "backend/second.py", "new": "backend/group/second.py", "type": "path"},
            ]
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("backend/group", result.stderr)
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())

    def test_old_path_scope_still_protects_new_names_after_move(self):
        self.write("backend/legacy/entry.py", '"Provider"\n')
        self.git("add", ".")
        entries = [
            {"old": "backend/legacy", "new": "backend/current", "type": "path"},
            {
                "old": "Provider",
                "new": "Provider Record",
                "type": "doctype",
                "paths": ["backend/legacy/*"],
            },
            {
                "old": "Record",
                "new": "Entry",
                "type": "identifier",
                "paths": ["backend/current/*"],
            },
        ]
        result = self.rename(entries)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "backend/current/entry.py").read_text(), '"Provider Record"\n')
        rerun = self.rename(entries, "--dry-run")
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertIn("0 tracked file(s)", rerun.stdout)

    def test_keycloak_proposals_use_specific_code_scopes(self):
        sources = {
            "backend/identity/keycloak/tests/test_realm_dosyalari.py": (
                "anahtarlar = ()\nornek = 'sample.ornek@example.test'\n"
                "for satir in ornek.splitlines():\n    pass\n",
                "keys = ()\nexample = 'sample.ornek@example.test'\n"
                "for line in example.splitlines():\n    pass\n",
            ),
            "backend/identity/keycloak/tests/test_eklentiler.py": (
                "def _cerezli_acici():\n    return yonetici\n",
                "def _cookie_opener():\n    return admin_token\n",
            ),
            "backend/libs/oidc_verify/tests/test_oidc_verify.py": (
                "def erisim():\n    return saglayici\n",
                "def access():\n    return provider\n",
            ),
            "backend/other/sample.py": ("ornek = True\n", "ornek = True\n"),
        }
        for path, (source, _) in sources.items():
            self.write(path, source)
        self.git("add", ".")
        result = self.rename(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        names_after = {
            "test_realm_dosyalari.py": "test_realm_files.py",
            "test_eklentiler.py": "test_extensions.py",
        }
        for path, (_, expected) in sources.items():
            target = Path(path)
            target = target.with_name(names_after.get(target.name, target.name))
            with self.subTest(path=path):
                self.assertEqual((self.root / target).read_text(), expected)
