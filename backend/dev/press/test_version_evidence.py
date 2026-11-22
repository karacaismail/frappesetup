"""Keep the recorded Press source audit complete without network or Git access."""

import ast
import copy
import json
import re
import shlex
import unittest
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
BASELINE = "7a4384d5eec9f0f0dce4124e9dd48b106e51222f"
HEADS = {
    "develop": "d7d1cd2ae8352b8a78f0aefb210f9ea6d83cc410",
    "master": "a9a7acd487902e54253d38bd9ef79ce52be9bc86",
}
REMOTE = "https://github.com/frappe/press.git"
HISTORY_PATHS = {
    "press/press/doctype/deploy_candidate/cache_utils.py",
    "press/saas/doctype/product_trial_request/product_trial_request.py",
}
COOKIE_IMPORT = "from frappe.oauth import get_cookie_dict_from_headers"
UNPREFIXED_TAGS = ["0.2.0", "0.2.1", "0.3.0"]


def git_commands(markdown):
    """Read literal Git commands from executable shell fences, without running them."""
    commands = []
    for block in re.findall(r"^```(?:sh|bash|shell)\n(.*?)^```", markdown, re.MULTILINE | re.DOTALL):
        for line in block.replace("\\\n", " ").splitlines():
            if not line.lstrip().startswith("git "):
                continue
            words = shlex.split(line, comments=True)
            if ">" in words:
                words = words[: words.index(">")]
            for index, word in enumerate(words):
                if word in {"rev-list", "ls-remote"}:
                    commands.append(words[index:])
                    break
    return commands


class VersionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((DOCS / "evidence/press-python314-versions.json").read_text())
        cls.document = (DOCS / "press-python314-version-audit.md").read_text()

    def assert_history_commands(self, document):
        commands = git_commands(document)
        for head in HEADS.values():
            candidates = [
                command
                for command in commands
                if command[0] == "rev-list" and f"{BASELINE}..{head}" in command
            ]
            self.assertTrue(candidates, f"Missing pinned history command for {head}")
            self.assertTrue(
                any(
                    "--full-history" in command
                    and "--" in command
                    and set(command[command.index("--") + 1 :]) == HISTORY_PATHS
                    for command in candidates
                ),
                f"History command must retain full history and both source paths: {head}",
            )

    def assert_remote_commands(self, document):
        commands = [command for command in git_commands(document) if command[0] == "ls-remote"]
        for options, refs in [({"--tags", "--refs"}, []), ({"--heads"}, []), ({"--symref"}, ["HEAD"])]:
            self.assertTrue(
                any(
                    REMOTE in command
                    and options.issubset(command[1 : command.index(REMOTE)])
                    and command[command.index(REMOTE) + 1 :] == refs
                    for command in commands
                ),
                f"Missing official remote enumeration: {sorted(options)} {refs}",
            )

    def assert_cookies(self, evidence):
        for field in ["cookies_path", "cookies_snapshots", "cookies_blobs", "cookies_baseline"]:
            self.assertTrue(field in evidence, f"Missing cookies evidence: {field}")
        self.assertEqual(evidence["cookies_path"], "press/api/cookies.py")
        snapshots = evidence["cookies_snapshots"]
        blobs = evidence["cookies_blobs"]
        self.assertEqual(set(snapshots), set(evidence["snapshots"]))
        self.assertEqual(set(blobs), {blob for blob in snapshots.values() if blob is not None})
        for blob, measurement in blobs.items():
            self.assertRegex(blob, r"^[0-9a-f]{40}$")
            self.assertIn("line", measurement)
            self.assertIn("import", measurement)
            if measurement["import"] is None:
                self.assertIsNone(measurement["line"])
                continue
            self.assertIs(type(measurement["line"]), int)
            self.assertGreater(measurement["line"], 0)
            statements = ast.parse(measurement["import"]).body
            self.assertEqual(len(statements), 1)
            statement = statements[0]
            self.assertIsInstance(statement, ast.ImportFrom)
            self.assertEqual(statement.module, "frappe.oauth")
            self.assertEqual(statement.level, 0)
            self.assertIn("get_cookie_dict_from_headers", [alias.name for alias in statement.names])
        baseline = evidence["cookies_baseline"]
        self.assertEqual(baseline["commit"], BASELINE)
        self.assertIs(baseline["in_snapshots"], True)
        self.assertIn(BASELINE, snapshots)
        self.assertEqual(baseline["blob"], snapshots[BASELINE])
        self.assertIsNotNone(baseline["blob"])
        self.assertEqual(blobs[baseline["blob"]], {"line": 7, "import": COOKIE_IMPORT})

    def complete_fixture(self):
        evidence = copy.deepcopy(self.evidence)
        cookie_blob = "c" * 40
        evidence.update(
            cookies_path="press/api/cookies.py",
            cookies_snapshots=dict.fromkeys(evidence["snapshots"], cookie_blob),
            cookies_blobs={cookie_blob: {"line": 7, "import": COOKIE_IMPORT}},
            cookies_baseline={"commit": BASELINE, "blob": cookie_blob, "in_snapshots": True},
        )
        return evidence

    def command_fixture(self):
        paths = " ".join(sorted(HISTORY_PATHS))
        history = [
            f'git -C "$PRESS_REPO" rev-list --full-history {BASELINE}..{head} -- {paths}'
            for head in HEADS.values()
        ]
        remote = [
            f"git ls-remote {options} {REMOTE}{ref}"
            for options, ref in [("--tags --refs", ""), ("--heads", ""), ("--symref", " HEAD")]
        ]
        return "```sh\n" + "\n".join(history + remote) + "\n```\n"

    def test_document_preserves_full_history_commands(self):
        self.assert_history_commands(self.document)

    def test_document_enumerates_official_remote_refs(self):
        self.assert_remote_commands(self.document)

    def test_evidence_preserves_pinned_snapshot_coverage(self):
        evidence = self.evidence
        self.assertEqual(evidence["refs"][evidence["baseline"]], BASELINE)
        self.assertEqual({name: evidence["refs"][name] for name in HEADS}, HEADS)
        self.assertEqual(set(evidence["histories"]), set(HEADS.values()))
        self.assertEqual({evidence["cache_path"], evidence["telemetry_path"]}, HISTORY_PATHS)
        snapshots = set(evidence["refs"].values())
        for commits in evidence["histories"].values():
            snapshots.update(commits)
        self.assertEqual(set(evidence["snapshots"]), snapshots)
        self.assertEqual(len(snapshots), evidence["source_snapshot_count"])
        self.assertEqual(len(snapshots), 269)
        self.assertEqual(set(evidence["snapshots"].values()), set(evidence["telemetry_blobs"]))

    def test_evidence_records_unprefixed_tags(self):
        self.assertTrue("unprefixed_semver_tags" in self.evidence, "Missing unprefixed tag evidence")
        self.assertEqual(self.evidence["unprefixed_semver_tags"], UNPREFIXED_TAGS)

    def test_cookies_cover_every_snapshot_and_baseline(self):
        self.assert_cookies(self.evidence)

    def test_command_fixture_accepts_line_continuations(self):
        document = self.command_fixture().replace(" -- ", " " + chr(92) + "\n  -- ")
        self.assert_history_commands(document)
        self.assert_remote_commands(document)

    def test_command_fixture_accepts_output_redirection(self):
        lines = self.command_fixture().splitlines()
        document = "\n".join(
            line + ' > "$PRESS_REPO/evidence.txt"' if line.startswith("git ") else line for line in lines
        )
        self.assert_history_commands(document)
        self.assert_remote_commands(document)

    def test_history_commands_reject_narrowed_or_unpinned_scope(self):
        document = self.command_fixture()
        for original, replacement in [
            ("--full-history", ""),
            (BASELINE, "v0.154.1"),
            (HEADS["develop"], "develop"),
            (sorted(HISTORY_PATHS)[0], ""),
            ("```sh", "```text"),
        ]:
            with self.subTest(original=original), self.assertRaises(AssertionError):
                self.assert_history_commands(document.replace(original, replacement))

    def test_remote_commands_reject_missing_or_wrong_sources(self):
        document = self.command_fixture()
        for original, replacement in [
            ("--refs", ""),
            ("--heads", "--tags"),
            (" HEAD", ""),
            (REMOTE, "https://example.invalid/press.git"),
        ]:
            with self.subTest(original=original), self.assertRaises(AssertionError):
                self.assert_remote_commands(document.replace(original, replacement))

    def test_cookies_fixture_accepts_complete_evidence(self):
        self.assert_cookies(self.complete_fixture())

    def test_cookies_reject_missing_snapshot(self):
        evidence = self.complete_fixture()
        del evidence["cookies_snapshots"][HEADS["develop"]]
        with self.assertRaises(AssertionError):
            self.assert_cookies(evidence)

    def test_cookies_reject_orphan_blob(self):
        evidence = self.complete_fixture()
        evidence["cookies_blobs"]["d" * 40] = {"line": 7, "import": COOKIE_IMPORT}
        with self.assertRaises(AssertionError):
            self.assert_cookies(evidence)

    def test_cookies_reject_mismatched_baseline(self):
        for field, invalid_entry in [
            ("commit", HEADS["develop"]),
            ("blob", "d" * 40),
            ("in_snapshots", False),
        ]:
            evidence = self.complete_fixture()
            evidence["cookies_baseline"][field] = invalid_entry
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.assert_cookies(evidence)

    def test_cookies_reject_invalid_import_measurements(self):
        for measurement in [
            {"line": 0, "import": COOKIE_IMPORT},
            {"line": True, "import": COOKIE_IMPORT},
            {"line": "7", "import": COOKIE_IMPORT},
            {"line": None, "import": COOKIE_IMPORT},
            {"line": 7, "import": None},
            {"line": 7, "import": "from frappe.oauth import another_function"},
            {"line": 7, "import": "from other_package import get_cookie_dict_from_headers"},
        ]:
            evidence = self.complete_fixture()
            evidence["cookies_blobs"]["c" * 40] = measurement
            with self.subTest(measurement=measurement), self.assertRaises(AssertionError):
                self.assert_cookies(evidence)

    def test_cookies_fixture_records_absent_path_and_import(self):
        evidence = self.complete_fixture()
        evidence["cookies_snapshots"][HEADS["develop"]] = None
        evidence["cookies_snapshots"][HEADS["master"]] = "d" * 40
        evidence["cookies_blobs"]["d" * 40] = {"line": None, "import": None}
        self.assert_cookies(evidence)


if __name__ == "__main__":
    unittest.main()
