"""Check that the Press provisioning Ansible version is pinned in one place and recorded."""

import re
import unittest
from pathlib import Path

PRESS_DEV = Path(__file__).resolve().parent
REPO = PRESS_DEV.parents[2]
PINS = PRESS_DEV / "ansible-requirements.txt"
LOCK = PRESS_DEV / "ansible-requirements.lock.txt"
DECISION = REPO / "backend/docs/decisions/0018-press-ansible-python314.md"


def read_pins(text):
    pins = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9.]*)", line)
        if match is None:
            raise AssertionError(f"not an exact pin: {line!r}")
        pins[match.group(1).lower()] = match.group(2)
    return pins


class AnsiblePinTest(unittest.TestCase):
    def test_requirements_pin_the_community_package_and_core_exactly(self):
        pins = read_pins(PINS.read_text())
        self.assertEqual(set(pins), {"ansible", "ansible-core"})
        major = int(pins["ansible"].split(".")[0])
        core = tuple(int(part) for part in pins["ansible-core"].split(".")[:2])
        # ansible-core 2.20 is the first control-node release that supports Python 3.14.
        self.assertGreaterEqual(core, (2, 20))
        # ansible 13 ships ansible-core 2.20; each later major ships the next core minor.
        self.assertEqual(core, (2, major + 7))

    def test_development_image_overrides_press_pin_with_the_same_versions(self):
        pins = read_pins(PINS.read_text())
        overrides = read_pins((PRESS_DEV / "uv-overrides.txt").read_text())
        for name, version in pins.items():
            with self.subTest(name=name):
                self.assertEqual(overrides.get(name), version)

    def test_hash_lock_covers_exact_direct_pins_and_transitive_packages(self):
        entries = [
            entry
            for entry in LOCK.read_text().replace("\\\n", "").splitlines()
            if entry and not entry.startswith("#")
        ]
        locked_pins = {}
        for entry in entries:
            requirement, *hashes = entry.split(" --hash=sha256:")
            with self.subTest(requirement=requirement.strip()):
                locked_pins.update(read_pins(requirement.split(";", 1)[0]))
                self.assertTrue(hashes)
                for digest in hashes:
                    self.assertRegex(digest.strip(), r"^[0-9a-f]{64}$")
        direct_pins = read_pins(PINS.read_text())
        self.assertGreater(len(locked_pins), len(direct_pins))
        self.assertEqual({name: locked_pins[name] for name in direct_pins}, direct_pins)

    def test_decision_note_and_readiness_guide_record_the_pinned_versions(self):
        pins = read_pins(PINS.read_text())
        decision = DECISION.read_text()
        guide = (PRESS_DEV / "provisioning-readiness.md").read_text()
        for name, version in pins.items():
            with self.subTest(name=name):
                self.assertIn(f"{name}=={version}", decision)
                self.assertIn(version, guide)
