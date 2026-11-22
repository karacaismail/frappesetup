"""Shared helpers for tests that need the pinned Ansible on a Python 3.14 interpreter.

Set PRESS_TEST_ANSIBLE_PYTHON to an interpreter that has backend/dev/press/ansible-requirements.txt
installed, and PRESS_TEST_PRESS_SOURCE to a clean Press checkout at the pinned tag. Inside the
disposable bench both are env/bin/python and apps/press.
"""

import os
import re
import subprocess
import unittest
from pathlib import Path

PRESS_DEV = Path(__file__).resolve().parent
REPO = PRESS_DEV.parents[2]
PYTHON = os.environ.get("PRESS_TEST_ANSIBLE_PYTHON")
PRESS_SOURCE = os.environ.get("PRESS_TEST_PRESS_SOURCE")


def requires_ansible_environment(cls):
    return unittest.skipUnless(
        PYTHON and PRESS_SOURCE,
        "set PRESS_TEST_ANSIBLE_PYTHON and PRESS_TEST_PRESS_SOURCE",
    )(cls)


def pinned_core_version():
    text = (PRESS_DEV / "ansible-requirements.txt").read_text()
    return re.search(r"(?m)^ansible-core==(\S+)", text).group(1)


def assert_interpreter_matches_pins(test):
    """Fail loudly when the interpreter under test does not carry the pinned ansible-core."""
    completed_process = subprocess.run(
        [
            PYTHON,
            "-c",
            "import ansible.release, sys; print(*sys.version_info[:2], ansible.release.__version__)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    major, minor, core = completed_process.stdout.split()
    test.assertEqual(core, pinned_core_version())
    test.assertEqual((major, minor), ("3", "14"), "the provisioning control node is Python 3.14")
