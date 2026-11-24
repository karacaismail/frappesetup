"""Keep temporary Press changes paired with a removal plan."""

import ast
import hashlib
import json
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REGISTRY = BACKEND / "dev/press/patch-registry.json"
PATCH_SCRIPT = "dev/press/patch-py314.sh"
OVERRIDES = "dev/press/uv-overrides.txt"
PATCH_DIR = "deploy/images/press-patches"
REQUIRED_FIELDS = ("source", "owner", "test", "removal_condition", "upstream")
PRESS_TR_HOOKS = "apps/press_tr/press_tr/hooks.py"
# G-7: Press issues that press_tr closes until Press accepts the upstream proposal.
PRESS_TR_FIXES = {
    "site-validate-encryption-key": "press_tr.backup_keys.validate_site_keys",
    "agent-complete-setup-wizard": "press_tr.setup_wizard.start_setup_wizard",
    "cloud-fixture-defaults": "press_tr.fixture_cleanup.disable_cloud_defaults",
}
FIX_FIELDS = ("id", "hook", "owner", "test", "removal_condition", "upstream", "upstream_status")
UPSTREAM_STATUSES = ("draft", "sent")


def heading_anchor(heading):
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s", "-", text)


def assert_test_exists(case, reference):
    match = re.fullmatch(r"([^:]+\.py)::([A-Za-z_]\w*)\.([A-Za-z_]\w*)", reference)
    case.assertIsNotNone(match, "Expected path.py::Class.method")
    filename, class_name, method_name = match.groups()
    path = (BACKEND / filename).resolve()
    case.assertTrue(path.is_relative_to(BACKEND), "Test must be inside backend")
    case.assertTrue(path.is_file(), f"Test file not found: {filename}")
    module = ast.parse(path.read_bytes(), filename=filename)
    test_class = next(
        (node for node in module.body if isinstance(node, ast.ClassDef) and node.name == class_name),
        None,
    )
    case.assertIsNotNone(test_class, f"Test class not found: {class_name}")
    case.assertTrue(
        any(isinstance(node, ast.FunctionDef) and node.name == method_name for node in test_class.body),
        f"Test method not found: {class_name}.{method_name}",
    )


class PressPatchRegistryTest(unittest.TestCase):
    def test_every_patch_has_one_complete_record(self):
        self.assertTrue(REGISTRY.is_file(), "Temporary Press patches have no registry")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        script = (BACKEND / PATCH_SCRIPT).read_bytes()
        expected = {
            (PATCH_SCRIPT, patch_id.decode("ascii"))
            for patch_id in re.findall(rb"^# patch-id: ([a-z0-9-]+)$", script, re.MULTILINE)
        }
        expected.add((OVERRIDES, ""))
        expected.update(
            (path.relative_to(BACKEND).as_posix(), "")
            for path in (BACKEND / PATCH_DIR).glob("*.patch")
        )

        actual = set()
        for record in registry["patches"]:
            for field in REQUIRED_FIELDS:
                self.assertTrue(
                    isinstance(record.get(field), str) and record[field].strip(),
                    f"{record.get('source')}: missing {field}",
                )
            key = (record["source"], record.get("id", ""))
            self.assertNotIn(key, actual, f"Duplicate patch record: {key}")
            actual.add(key)

        self.assertFalse(expected - actual, f"Unregistered patches: {sorted(expected - actual)}")
        self.assertFalse(actual - expected, f"Records without patches: {sorted(actual - expected)}")

    def test_registered_tests_exist(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for record in registry["patches"]:
            reference = record["test"]
            with self.subTest(source=record["source"], reference=reference):
                assert_test_exists(self, reference)

    def test_unmarked_script_or_override_changes_require_review(self):
        self.assertTrue(REGISTRY.is_file(), "Temporary Press patches have no registry")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for source in (PATCH_SCRIPT, OVERRIDES):
            with self.subTest(source=source):
                digest = hashlib.sha256((BACKEND / source).read_bytes()).hexdigest()
                self.assertEqual(
                    digest,
                    registry["sha256"][source],
                    f"{source} changed: review its patch records before updating the digest",
                )

    def test_press_tr_fixes_have_upstream_proposals(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        fixes = registry.get("press_tr_fixes", [])
        hooks = (BACKEND / PRESS_TR_HOOKS).read_text(encoding="utf-8")
        seen = {}
        for record in fixes:
            for field in FIX_FIELDS:
                self.assertTrue(
                    isinstance(record.get(field), str) and record[field].strip(),
                    f"{record.get('id')}: missing {field}",
                )
            self.assertNotIn(record["id"], seen, f"Duplicate press_tr fix: {record['id']}")
            seen[record["id"]] = record["hook"]
            with self.subTest(fix=record["id"]):
                self.assertIn(f'"{record["hook"]}"', hooks, "The fix must run from press_tr hooks")
                assert_test_exists(self, record["test"])
                self.assertIn(record["upstream_status"], UPSTREAM_STATUSES)
                document, _separator, anchor = record["upstream"].partition("#")
                path = (BACKEND / document).resolve()
                self.assertTrue(path.is_relative_to(BACKEND) and path.is_file(), f"No proposal: {document}")
                headings = re.findall(r"^#{1,6} (.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
                self.assertIn(anchor, {heading_anchor(heading) for heading in headings}, "No proposal heading")
        self.assertEqual(seen, PRESS_TR_FIXES, "Every Press issue closed in press_tr needs a record")
