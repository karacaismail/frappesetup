"""G-11: closure evidence for Press access rules.

The checks need the pinned Press source, but not a database:
- Frappe 16 runs `before_request` hooks before it authenticates a request.
- press_tr adds only documented routes to `press.auth.ALLOWED_PATHS`, once.
- Website users reach documented press_tr routes and nothing else under `/api/`.
- press_tr DocTypes stay out of the Press dashboard client.
- A team cannot read another team's record through the dashboard client.
"""

import ast
import importlib
import inspect
import json
import pkgutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
import frappe.app
import press.auth
from press.api import client

import press_tr
import press_tr.api
from press_tr import hooks
from press_tr.press_identity import request_policy

APP_ROOT = Path(press_tr.__file__).resolve().parent


def raise_exception(message, exception=frappe.ValidationError, *args, **kwargs):
	raise exception(message)


def called_names(node):
	return [
		call.func.id
		for call in ast.walk(node)
		if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
	]


def press_tr_api_methods():
	for module in pkgutil.iter_modules(press_tr.api.__path__):
		if not module.name.startswith("test_"):
			importlib.import_module(f"press_tr.api.{module.name}")
	return sorted(
		f"{method.__module__}.{method.__qualname__}"
		for method in map(inspect.unwrap, frappe.whitelisted)
		if method.__module__.split(".")[:2] == ["press_tr", "api"]
	)


def press_tr_doctypes():
	return sorted(
		json.loads(path.read_text())["name"]
		for path in APP_ROOT.glob("*/doctype/*/*.json")
		if path.stem == path.parent.name
	)


class PressAccessTest(unittest.TestCase):
	def run_before_request(self, path, allowed_paths):
		facade = Mock()
		facade.request.path = path
		facade.form_dict.get.return_value = None
		facade.get_request_header.return_value = "token key:secret"
		with (
			patch.object(request_policy, "frappe", facade),
			patch.object(request_policy, "request_target", return_value=(Mock(), {})),
			patch.object(request_policy, "blocked_identity_targets", return_value=set()),
			patch.object(request_policy, "machine_targets", return_value={}),
			patch.object(request_policy, "block_team_invitation"),
			patch.object(press.auth, "ALLOWED_PATHS", allowed_paths),
		):
			request_policy.before_request()

	def press_auth_allows(self, path, allowed_paths):
		facade = Mock()
		facade.form_dict.cmd = None
		facade.request.path = path
		facade.request.method = "POST"
		facade.session.user = "member@example.test"
		facade.get_cached_value.return_value = "Website User"
		facade.AuthenticationError = frappe.AuthenticationError
		facade.throw.side_effect = raise_exception
		with (
			patch.object(press.auth, "frappe", facade),
			patch.object(press.auth, "log"),
			patch.object(press.auth, "ALLOWED_PATHS", allowed_paths),
		):
			try:
				press.auth.hook()
			except frappe.AuthenticationError:
				return False
		return True

	def test_frappe_16_runs_before_request_before_authentication(self):
		self.assertEqual(frappe.__version__.split(".")[0], "16")
		module = ast.parse(Path(frappe.app.__file__).read_text())
		functions = {
			node.name: node
			for node in module.body
			if isinstance(node, ast.FunctionDef) and node.name in {"application", "init_request"}
		}
		calls = called_names(functions["application"])
		self.assertLess(calls.index("init_request"), calls.index("validate_auth"))
		hook_names = {
			call.args[0].value
			for call in ast.walk(functions["init_request"])
			if isinstance(call, ast.Call)
			and ast.unparse(call.func) == "frappe.get_hooks"
			and call.args
			and isinstance(call.args[0], ast.Constant)
		}
		self.assertIn("before_request", hook_names)
		self.assertIn("press_tr.press_identity.request_policy.before_request", hooks.before_request)

	def test_every_press_tr_api_method_has_a_documented_route(self):
		methods = press_tr_api_methods()
		self.assertTrue(methods)
		# G-11 names `/api/method/press_tr.api.` as a wildcard. press_tr lists each method instead,
		# so a new method stays closed until it is documented. Every current method is reachable.
		for method in methods:
			with self.subTest(method=method):
				allowed_paths = []
				self.run_before_request(f"/api/method/{method}", allowed_paths)
				self.assertEqual(allowed_paths, [f"/api/method/{method}"])

	def test_documented_route_is_added_to_press_allowlist_once(self):
		allowed_paths = []
		path = "/api/method/press_tr.api.account.request_deletion"
		self.run_before_request(path, allowed_paths)
		self.run_before_request(path + "/", allowed_paths)
		self.assertEqual(allowed_paths, [path])

	def test_undocumented_press_tr_route_stays_closed_to_website_users(self):
		allowed_paths = []
		path = "/api/method/press_tr.api.account.undocumented"
		self.run_before_request(path, allowed_paths)
		self.assertEqual(allowed_paths, [])
		self.assertFalse(self.press_auth_allows(path, allowed_paths))

	def test_press_auth_allows_documented_routes_and_denies_other_api_paths(self):
		allowed_paths = []
		documented = "/api/method/press_tr.api.account.request_deletion"
		self.run_before_request(documented, allowed_paths)
		self.assertTrue(self.press_auth_allows(documented, allowed_paths))
		for path in (
			"/api/method/frappe.client.get_list",
			"/api/resource/PTR Identity Link",
			"/api/v2/document/PTR Keycloak Session",
		):
			with self.subTest(path=path):
				self.assertFalse(self.press_auth_allows(path, allowed_paths))

	def test_press_tr_doctypes_are_closed_to_the_dashboard_client(self):
		doctypes = press_tr_doctypes()
		self.assertTrue(doctypes)
		team = SimpleNamespace(name="team-a")
		with (
			patch.object(client.frappe, "throw", side_effect=raise_exception),
			patch.object(client.frappe.local, "team", Mock(return_value=team), create=True),
		):
			self.assertTrue(client.check_permissions("Site"))
			for doctype in doctypes:
				with self.subTest(doctype=doctype):
					self.assertNotIn(doctype, client.ALLOWED_DOCTYPES)
					with self.assertRaises(frappe.PermissionError):
						client.check_permissions(doctype)

	def test_press_tr_has_no_dashboard_document_methods(self):
		# Press Method Permission rows guard dashboard document methods. press_tr has none.
		for path in APP_ROOT.rglob("*.py"):
			with self.subTest(path=path.relative_to(APP_ROOT)):
				self.assertNotIn("dashboard_whitelist", path.read_text())

	def test_dashboard_client_denies_another_teams_record(self):
		facade = Mock()
		facade.local.team.return_value = SimpleNamespace(name="team-a")
		facade.throw.side_effect = raise_exception
		facade.PermissionError = frappe.PermissionError
		with patch.object(client, "frappe", facade):
			facade.db.get_value.return_value = "team-a"
			self.assertTrue(client.is_owned_by_team("Site", "own.example.test"))
			facade.db.get_value.return_value = "team-b"
			with self.assertRaises(frappe.PermissionError):
				client.is_owned_by_team("Site", "other.example.test")
		facade.db.get_value.assert_called_with("Site", "other.example.test", "team")


if __name__ == "__main__":
	unittest.main()
