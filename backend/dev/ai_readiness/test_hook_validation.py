"""Exercise the supported hook declaration form through hook_checks."""

import ast
import unittest
from pathlib import Path

from gate import hook_checks
from source import assignments


def check(source):
    tree = ast.parse(source)
    bindings = dict(pair for item in tree.body for pair in assignments(item))
    findings = []

    def emit(path, line, rule, message):
        findings.append((line, rule, message))

    hooks = hook_checks(Path("hooks.py"), tree, bindings, emit)
    return hooks, findings


class HookValidationTests(unittest.TestCase):
    def test_direct_assignments_still_register_hooks(self):
        source = (
            "ai_tools = ['sample.tools.declare']\n"
            "override_whitelisted_methods = {'sample.api.old': 'sample.api.new'}\n"
        )
        (tools, overrides), findings = check(source)
        self.assertEqual(list(tools), ["sample.tools.declare"])
        self.assertEqual(overrides["sample.api.old"][0], "sample.api.new")
        self.assertEqual(findings, [])

    def test_ai_tools_requires_one_direct_top_level_assignment(self):
        cases = (
            ("ai_tools = []\nai_tools += ['sample.tools.declare']", 2),
            ("ai_tools = []\nai_tools.extend(['sample.tools.declare'])", 2),
            ("ai_tools = []\nai_tools.append('sample.tools.declare')", 2),
            ("if enabled:\n    ai_tools = ['sample.tools.declare']", 2),
            ("ai_tools = []\nai_tools = ['sample.tools.declare']", 2),
            ("ai_tools = other = []", 1),
            ("from sample.hooks import ai_tools", 1),
        )
        for source, line in cases:
            with self.subTest(source=source):
                _, findings = check(source)
                self.assertEqual([(row[0], row[1]) for row in findings], [(line, "sql")])
                self.assertIn("ai_tools", findings[0][2])

    def test_override_requires_one_direct_top_level_assignment(self):
        cases = (
            ("override_whitelisted_methods = {}\noverride_whitelisted_methods.update({})", 2),
            ("if enabled:\n    override_whitelisted_methods = {}", 2),
            ("override_whitelisted_methods: dict = {}", 1),
        )
        for source, line in cases:
            with self.subTest(source=source):
                _, findings = check(source)
                self.assertEqual([(row[0], row[1]) for row in findings], [(line, "endpoint")])
                self.assertIn("override_whitelisted_methods", findings[0][2])
