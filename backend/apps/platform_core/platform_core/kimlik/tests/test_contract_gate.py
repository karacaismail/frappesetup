"""The contract lists the gated functions exactly as the code serves them (third review, minor finding).

- every replaced Frappe address in `override_whitelisted_methods` is in the `x-frappe-original` list of the
  target operation (contract rule from the orchestrator),
- the HTTP methods of each wrapper equal the operations of its path,
- every wrapper whitelists its methods explicitly.
"""

import os

import frappe
import yaml
from frappe.tests import IntegrationTestCase

from platform_core.kimlik import login_policy

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACT = os.path.join(APP, "..", "..", "..", "contracts", "platform_core-kimlik.openapi.yaml")
PREFIX = "platform_core.kimlik.login_policy."


def _paths() -> dict:
	with open(CONTRACT, encoding="utf-8") as handle:
		return yaml.safe_load(handle)["paths"]


class TestContractGate(IntegrationTestCase):
	def test_every_override_is_listed_in_x_frappe_original(self):
		paths = _paths()
		overrides = frappe.get_hooks("override_whitelisted_methods")
		missing = []
		for original, targets in overrides.items():
			target = targets[-1]
			if not target.startswith(PREFIX):
				continue
			operations = paths.get(f"/{target}", {})
			if not operations or any(
				original not in (op.get("x-frappe-original") or []) for op in operations.values()
			):
				missing.append(original)
		self.assertEqual(missing, [])

	def test_http_methods_of_each_wrapper_match_the_contract(self):
		paths = _paths()
		problems = []
		for name, methods in login_policy.GATED_FUNCTIONS.values():
			verbs = sorted(paths.get(f"/{PREFIX}{name}", {}))
			if verbs != sorted(m.lower() for m in methods):
				problems.append(f"{name}: code {methods}, contract {verbs}")
			function = getattr(login_policy, name)
			allowed = frappe.allowed_http_methods_for_whitelisted_func.get(function)
			if sorted(allowed or []) != sorted(methods):
				problems.append(f"{name}: whitelisted {allowed}, declared {methods}")
		self.assertEqual(problems, [])

	def test_every_gated_function_is_overridden(self):
		overrides = frappe.get_hooks("override_whitelisted_methods")
		self.assertEqual(
			{original: overrides.get(original, [None])[-1] for original in login_policy.GATED_FUNCTIONS},
			login_policy.override_map(),
		)
