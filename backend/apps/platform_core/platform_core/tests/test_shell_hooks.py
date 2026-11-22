import ast
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.datastructures import Headers
from werkzeug.wrappers import Response

from platform_core.hooks import doc_events


class TestShellPermissionHooks(IntegrationTestCase):
	def test_security_header_hook_is_installed_once(self):
		hook = "platform_core.shell.headers.add_security_headers"
		self.assertEqual(frappe.get_hooks("after_request").count(hook), 1)

	def test_security_header_hook_preserves_existing_values(self):
		from platform_core.shell.headers import add_security_headers

		response = Response(headers={"X-Frame-Options": "DENY"})
		pending = Headers({"Referrer-Policy": "no-referrer"})
		with patch.object(frappe.local, "response_headers", pending, create=True):
			add_security_headers(response)
		self.assertEqual(response.headers.getlist("X-Frame-Options"), ["DENY"])
		self.assertEqual(response.headers.getlist("X-Content-Type-Options"), ["nosniff"])
		self.assertNotIn("Referrer-Policy", response.headers)
		self.assertEqual(pending.getlist("Referrer-Policy"), ["no-referrer"])

	def test_security_header_hook_preserves_existing_csp(self):
		from platform_core.shell.headers import add_security_headers

		name = "Content-Security-Policy"
		policy = "default-src 'none'"
		for apply_pending in (False, True):
			with self.subTest(apply_pending=apply_pending):
				response = Response(headers={} if apply_pending else {name: policy})
				pending = Headers({name.lower(): policy} if apply_pending else {})
				with patch.object(frappe.local, "response_headers", pending, create=True):
					add_security_headers(response)
				self.assertEqual(response.headers.getlist(name), [] if apply_pending else [policy])
				self.assertEqual(pending.getlist(name), [policy] if apply_pending else [])

	def test_installed_auth_guard_follows_credentials_hooks(self):
		hooks = frappe.get_hooks("auth_hooks")
		guard = "platform_core.shell.native_metadata.guard_native_metadata"
		self.assertEqual(hooks.count(guard), 1)
		for name in (
			"platform_core.identity.service_token.validate",
			"platform_core.ai.agent_token.authenticate_request",
		):
			parts = name.split(".")
			module = Path(frappe.get_app_path(parts[0], *parts[1:-2], parts[-2] + ".py"))
			if module.is_file():
				self.assertIn(name, hooks)
			if name in hooks:
				self.assertLess(hooks.index(name), hooks.index(guard))

	def test_website_request_guard_is_installed(self):
		self.assertEqual(
			frappe.get_hooks("before_request").count(
				"platform_core.shell.native_metadata.guard_website_rpc_before_request"
			),
			1,
		)

	def test_list_hooks_have_one_assignment(self):
		path = Path(frappe.get_app_path("platform_core", "hooks.py"))
		tree = ast.parse(path.read_text(encoding="utf-8"))
		for name in (
			"auth_hooks",
			"after_build",
			"after_request",
			"clear_cache",
			"before_request",
			"doc_events",
			"website_user_allowed_methods",
		):
			assignments = [
				node
				for node in tree.body
				if isinstance(node, ast.Assign)
				and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
			]
			self.assertEqual(len(assignments), 1, name)

		dictionary = next(
			node.value
			for node in tree.body
			if isinstance(node, ast.Assign)
			and any(isinstance(target, ast.Name) and target.id == "doc_events" for target in node.targets)
		)
		for level in (dictionary, *dictionary.values):
			keys = [ast.literal_eval(key) for key in level.keys]
			self.assertEqual(len(keys), len(set(keys)), keys)
		for events in dictionary.values:
			for handlers in events.values:
				self.assertIsInstance(handlers, ast.List)

	def test_installed_shell_permission_hooks_invalidate_cached_permissions(self):
		installed = frappe.get_hooks("doc_events")
		for doctype in (
			"User",
			"Role",
			"Role Profile",
			"User Permission",
			"Custom DocPerm",
			"DocType",
			"Custom Field",
			"Property Setter",
			"PLT Access Rule",
		):
			for event in ("on_update", "on_trash"):
				self.assertIn(
					"platform_core.shell.cache.invalidate_permissions",
					installed[doctype][event],
					(doctype, event),
				)

	def test_permission_hook_doctypes_exist_on_the_site(self):
		for doctype, events in doc_events.items():
			if not any(
				"platform_core.shell.cache.invalidate_permissions" in handlers for handlers in events.values()
			):
				continue
			if doctype == "PLT Access Rule" and not frappe.db.exists("Module Def", "Access"):
				continue
			with self.subTest(doctype=doctype):
				self.assertEqual(frappe.db.exists("DocType", doctype), doctype)
