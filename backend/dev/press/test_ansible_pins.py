"""Check that the Press provisioning Ansible version is pinned in one place and recorded."""

import re
import unittest
from pathlib import Path

PRESS_DEV = Path(__file__).resolve().parent
REPO = PRESS_DEV.parents[2]
PINS = PRESS_DEV / "ansible-requirements.txt"
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

    def test_decision_note_and_readiness_guide_record_the_pinned_versions(self):
        pins = read_pins(PINS.read_text())
        decision = DECISION.read_text()
        guide = (PRESS_DEV / "provisioning-readiness.md").read_text()
        for name, version in pins.items():
            with self.subTest(name=name):
                self.assertIn(f"{name}=={version}", decision)
                self.assertIn(version, guide)
