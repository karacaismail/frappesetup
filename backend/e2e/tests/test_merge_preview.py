"""Exercise the preview command without Docker or the developer's Git repository."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
COMMAND = SUITE / "bin" / "merge-preview"
ORDER = (SUITE / "preview" / "branches.txt").read_text().split()
HOOKS = Path("backend/apps/platform_core/platform_core/hooks.py")
TRANSLATIONS = HOOKS.parent / "translations/tr.csv"


class MergePreviewTest(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(dir=os.environ.get("PANE_SCRATCH_DIR"))
        self.addCleanup(self.sandbox.cleanup)
        self.root = Path(self.sandbox.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.artifacts = self.root / "scratch"
        self.env = {
            **os.environ,
            "PANE_SCRATCH_DIR": str(self.artifacts),
            "GIT_AUTHOR_NAME": "karacaismail",
            "GIT_AUTHOR_EMAIL": "35493655+karacaismail@users.noreply.github.com",
        }
        for variable in ("GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            self.env.pop(variable, None)
        self.git("init", "-b", "backend")
        self.git("config", "user.name", self.env["GIT_AUTHOR_NAME"])
        self.git("config", "user.email", self.env["GIT_AUTHOR_EMAIL"])
        self.commit_file(HOOKS, 'auth_hooks = ["base"]\n')
        self.commit_file(Path("unknown.txt"), "base\n")
        for name in ORDER:
            self.git("branch", name)

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], env=self.env, text=True, stderr=subprocess.PIPE
        )

    def commit_file(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        self.git("add", "--", str(path))
        self.git("commit", "-m", "Test verisini hazırla")

    def refs(self):
        return self.git("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")

    def preview(self):
        before = self.refs()
        result = subprocess.run([str(COMMAND), "--merge-only"], cwd=self.repo, env=self.env, text=True, capture_output=True)
        [report] = self.artifacts.glob("merge-preview-*/report.md")
        self.assertEqual(before, self.refs())
        self.assertFalse((report.parent / "worktree").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")
        return result, report.read_text()

    def test_preserves_hook_lists_in_frozen_order_and_removes_temporary_refs(self):
        for name, hook in zip(ORDER, ("first", "second")):
            self.git("switch", name)
            self.commit_file(HOOKS, f'auth_hooks = ["base", "{hook}"]\ndoc_events = {{"Role": {{"on_trash": "{hook}"}}}}\n')
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"| {HOOKS} |", report)
        self.assertIn(f"| {ORDER[1]} | Birleştirildi |", report)
        self.assertIn("Kanca listeleri korundu.", report)
        head = re.search(r"Önizleme commit'i `([0-9a-f]+)`", report)[1]
        hooks = self.git("show", f"{head}:{HOOKS}")
        self.assertIn("auth_hooks = ['base', 'first', 'second']", hooks)
        self.assertIn("'on_trash': ['first', 'second']", hooks)
        self.assertLess(report.index(f"| {ORDER[0]} |"), report.index(f"| {ORDER[1]} |"))

    def test_allows_a_change_to_app_metadata(self):
        self.commit_file(HOOKS, 'auth_hooks = ["base"]\napp_title = "Old name"\n')
        self.git("switch", ORDER[0])
        self.git("merge", "--ff-only", "backend")
        self.commit_file(HOOKS, 'auth_hooks = ["base"]\napp_title = "New name"\n')
        self.git("switch", "backend")
        result, _ = self.preview()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_applies_the_approved_werkzeug_constraint(self):
        dependencies = HOOKS.parents[1] / "pyproject.toml"
        template = '[project]\ndependencies = [\n    "{}"\n]\n'
        self.commit_file(dependencies, template.format("frappe"))
        for name, constraint in zip(ORDER, ("Werkzeug>=3.1.9,<4", "Werkzeug~=3.1.9")):
            self.git("switch", name)
            self.git("merge", "--ff-only", "backend")
            self.commit_file(dependencies, template.format(constraint))
        self.git("switch", "backend")

        result, report = self.preview()

        self.assertEqual(result.returncode, 0, report)
        head = re.search(r"Önizleme commit'i `([0-9a-f]+)`", report)[1]
        merged = self.git("show", f"{head}:{dependencies}")
        self.assertIn('"Werkzeug~=3.1.9"', merged)
        self.assertNotIn("Werkzeug>=3.1.9,<4", merged)

    def test_blocks_an_unknown_conflict_and_still_cleans_up(self):
        for name in ORDER[:2]:
            self.git("switch", name)
            self.commit_file(Path("unknown.txt"), name + "\n")
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("| unknown.txt |", report)
        self.assertIn("Manual resolution required", report)
        self.assertIn("Geçici worktree ve dal kaldırıldı.", report)

    def test_rejects_a_lost_hook_even_without_a_git_conflict(self):
        self.git("switch", ORDER[0])
        self.commit_file(HOOKS, 'auth_hooks = ["replacement"]\n')
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Hook list lost an entry: hooks.auth_hooks", report)

    def test_reports_duplicate_hook_assignments_after_a_clean_git_merge(self):
        base = [f'anchor_{index} = "keep"\n' for index in range(16)]
        self.commit_file(HOOKS, "".join(base))
        for index, name in zip((2, 7, 12), ORDER):
            self.git("switch", name)
            self.git("merge", "--ff-only", "backend")
            content = base[:index] + [f'auth_hooks = ["{name}"]\n'] + base[index:]
            self.commit_file(HOOKS, "".join(content))
        self.git("switch", "backend")

        result, report = self.preview()

        self.assertEqual(result.returncode, 1)
        self.assertIn("## Yinelenen kanca atamaları", report)
        self.assertIn(f"| `{HOOKS}` | `auth_hooks` | 3, 9, 15 |", report)
        self.assertNotIn("Birleştirildi |", report)
        self.assertIn("Geçici worktree ve dal kaldırıldı.", report)

    def test_rejects_duplicate_nested_hook_keys_after_a_clean_merge(self):
        base = [f'    "Anchor{i}": "keep",\n' for i in range(16)]
        prefix = 'auth_hooks = ["base"]\ndoc_events = {\n'
        self.commit_file(HOOKS, prefix + "".join(base) + "}\n")
        for index, event, name in zip((2, 12), ("on_update", "validate"), ORDER):
            self.git("switch", name)
            self.git("merge", "--ff-only", "backend")
            added = f'    "User": {{"{event}": "app.{event}"}},\n'
            self.commit_file(HOOKS, prefix + "".join(base[:index] + [added] + base[index:]) + "}\n")
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Duplicate hook dictionary key: User", report)
        self.assertNotIn("Birleştirildi |", report)

    def test_rejects_lost_string_hook(self):
        prefix = 'auth_hooks = ["base"]\n'
        self.commit_file(HOOKS, prefix + 'doc_events = {"User": {"validate": "app.validate"}}\n')
        self.git("switch", ORDER[0])
        self.git("merge", "--ff-only", "backend")
        self.commit_file(HOOKS, prefix + 'doc_events = {"User": {"validate": "app.other_validate"}}\n')
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Hook string lost: hooks.doc_events.User.validate", report)

    def test_rejects_conflicting_translations_in_the_final_tree(self):
        self.git("switch", ORDER[0])
        self.commit_file(TRANSLATIONS, "Open,Aç\nOpen,Başlat\n")
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("A translation source and context have different values", report)

    def test_rejects_scheduler_registration_in_the_final_tree(self):
        self.git("switch", ORDER[0])
        self.commit_file(HOOKS, 'auth_hooks = ["base"]\nscheduler_events = {"daily": ["app.run"]}\n')
        self.git("switch", "backend")
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("scheduler_events is not allowed", report)

    def test_refuses_git_index_overrides_before_creating_artifacts(self):
        before = self.refs()
        env = {**self.env, "GIT_INDEX_FILE": str(self.root / "foreign-index")}
        result = subprocess.run([str(COMMAND), "--merge-only"], cwd=self.repo, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("GIT_INDEX_FILE", result.stderr)
        self.assertFalse(self.artifacts.exists())
        self.assertEqual(before, self.refs())

    def test_cleans_worktree_when_git_reports_a_partial_add_failure(self):
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        wrapper = fake_bin / "git"
        wrapper.write_text(
            '#!/bin/bash\n'
            'if [[ "$3" == worktree && "$4" == add ]]; then\n'
            '  "$PREVIEW_TEST_GIT" "$@" || exit $?\n'
            '  exit 42\n'
            'fi\n'
            'exec "$PREVIEW_TEST_GIT" "$@"\n'
        )
        wrapper.chmod(0o755)
        real_git = shutil.which("git")
        self.env.update(PREVIEW_TEST_GIT=real_git, PATH=str(fake_bin) + os.pathsep + self.env["PATH"])
        result, report = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Geçici worktree ve dal kaldırıldı.", report)

    def test_live_build_failure_cleans_its_builder_and_keeps_foreign_sidecars(self):
        runtime = SUITE / "preview" / "runtime.sh"
        preview = self.root / "runtime"
        worktree = preview / "worktree"
        dev = worktree / "backend" / "dev"
        keycloak = worktree / "backend" / "identity" / "keycloak"
        dev.mkdir(parents=True)
        keycloak.mkdir(parents=True)
        shutil.copy2(SUITE.parent / "dev" / "init_env.py", dev / "init_env.py")
        (keycloak / ".env.example").write_text("KC_BOOTSTRAP_ADMIN_USERNAME=preview\n")
        fake_bin = self.root / "docker-bin"
        fake_bin.mkdir()
        stubs = {
            "nc": "exit 1\n",
            "colima": "printf '%s\\n' 'Mem: 7 2 2 0 3 5'\n",
            "docker": (
                'if [[ "$1" == --context ]]; then [[ "$2" == colima ]] || exit 90; shift 2; fi\n'
                'printf "%s\\n" "$*" >> "$PREVIEW_TEST_DOCKER_LOG"\n'
                'case "$1 $2" in\n'
                '  "context inspect") echo unix:///test.sock ;;\n'
                '  "image inspect") [[ "$3" == frappe/erpnext:v16.55.0 ]] ;;\n'
                '  "container inspect") echo other-project ;;\n'
                '  "compose "*) [[ "$*" != *" build "* ]] || exit 42 ;;\n'
                'esac\n'
            ),
        }
        for name, script in stubs.items():
            executable = fake_bin / name
            executable.write_text("#!/bin/bash\n" + script)
            executable.chmod(0o755)
        log = self.root / "docker.log"
        env = {
            **self.env, "PATH": str(fake_bin) + os.pathsep + self.env["PATH"],
            "COLIMA_BIN": str(fake_bin / "colima"), "PANE_PORT": "6500", "FS_COLIMA_PROFILE": "default",
            "PREVIEW_DIR": str(preview), "PREVIEW_PROJECT": "fs-e2e-preview-test", "PREVIEW_TEST_DOCKER_LOG": str(log),
        }
        result = subprocess.run(["bash", str(runtime), str(worktree)], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 42, result.stderr)
        commands = log.read_text()
        self.assertIn("buildx rm fs-e2e-preview-test-builder", commands)
        self.assertIn("down --volumes", commands)
        self.assertNotIn("rm -f fs-e2e-preview-test-identity", commands)
        self.assertFalse(list(preview.glob("*.env")))
        self.assertFalse((preview / "docker-config").exists())


if __name__ == "__main__":
    unittest.main()
