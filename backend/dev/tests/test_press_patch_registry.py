"""Keep temporary Press changes paired with a removal plan."""

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
REQUIRED_FIELDS = ("source", "owner", "test", "removal_condition")


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
