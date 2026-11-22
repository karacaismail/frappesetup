"""Syntax-check the Press server provisioning playbooks with the pinned Ansible."""

import os
import subprocess
import unittest
from pathlib import Path

import ansible_test_env as env

PLAYBOOKS = ("server.yml", "self_hosted.yml")


@env.requires_ansible_environment
class ProvisioningPlaybookSyntaxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env.assert_interpreter_matches_pins(cls())

    def test_server_playbooks_parse_and_resolve_every_module(self):
        playbooks = Path(env.PRESS_SOURCE) / "press" / "playbooks"
        for playbook in PLAYBOOKS:
            with self.subTest(playbook=playbook):
                completed_process = subprocess.run(
                    [env.PYTHON, "-m", "ansible", "playbook", "--syntax-check", "-i", "localhost,", playbook],
                    cwd=playbooks,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "ANSIBLE_DEPRECATION_WARNINGS": "0", "ANSIBLE_LOCALHOST_WARNING": "0"},
                )
                self.assertEqual(
                    completed_process.returncode, 0, completed_process.stdout + completed_process.stderr
                )
                self.assertIn(f"playbook: {playbook}", completed_process.stdout)
