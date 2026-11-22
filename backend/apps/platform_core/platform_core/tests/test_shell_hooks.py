import ast
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from platform_core.hooks import doc_events


class TestShellPermissionHooks(IntegrationTestCase):
	def test_installed_auth_guard_follows_credentials_hooks(self):
		hooks = frappe.get_hooks("auth_hooks")
		guard = "platform_core.kabuk.native_metadata.guard_native_metadata"
		self.assertEqual(hooks.count(guard), 1)
		for name in (
			"platform_core.kimlik.service_token.validate",
			"platform_core.yapay_zeka.agent_token.authenticate_request",
		):
			parts = name.split(".")
			module = Path(frappe.get_app_path(parts[0], *parts[1:-2], parts[-2] + ".py"))
			if module.is_file():
				self.assertIn(name, hooks)
			if name in hooks:
				self.assertLess(hooks.index(name), hooks.index(guard))

	def test_list_hooks_have_one_assignment(self):
		path = Path(frappe.get_app_path("platform_core", "hooks.py"))
		tree = ast.parse(path.read_text(encoding="utf-8"))
		for name in ("auth_hooks", "after_build", "clear_cache"):
			assignments = [
				node
				for node in tree.body
				if isinstance(node, ast.Assign)
				and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
			]
			self.assertEqual(len(assignments), 1, name)

	def test_installed_access_rule_hooks_invalidate_cached_permissions(self):
		events = frappe.get_hooks("doc_events").get("Access Rule", {})
		for event in ("on_update", "on_trash"):
			self.assertIn("platform_core.kabuk.cache.invalidate_permissions", events.get(event, []))

	def test_permission_hook_doctypes_exist_on_the_site(self):
		for doctype, events in doc_events.items():
			if not any(str(hook).startswith("platform_core.kabuk.cache.") for hook in events.values()):
				continue
			if doctype == "Access Rule" and not frappe.db.exists("Module Def", "Erisim"):
				continue
			with self.subTest(doctype=doctype):
				self.assertEqual(frappe.db.exists("DocType", doctype), doctype)
