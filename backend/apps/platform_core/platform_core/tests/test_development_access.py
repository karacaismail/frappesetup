from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from platform_core import development_access, hooks


class TestDevelopmentAccess(TestCase):
	def check_request(self, path, *, command=None, **config):
		with patch.object(development_access, "frappe") as request_context:
			request_context.local.request = SimpleNamespace(path=path)
			request_context.form_dict = {"cmd": command}
			request_context.conf = config
			request_context.PermissionError = frappe.PermissionError
			request_context.throw.side_effect = frappe.PermissionError
			development_access.guard_development_endpoints()

	def test_hook_is_registered(self):
		self.assertIn("platform_core.development_access.guard_development_endpoints", hooks.before_request)

	def test_production_rejects_console_and_test_requests(self):
		console = "frappe.desk.doctype.system_console.system_console"
		fixture = "mobile_test_app.fixture.commit_probe"
		for path, command in (
			("/app/system-console", None),
			("/desk/system-console/", None),
			(f"/api/method/{console}.execute_code", None),
			(f"/api/v1/method/{console}.show_processlist", None),
			(f"/api/v2/method/{console}.execute_code", None),
			("/desk", f"{console}.execute_code"),
			(f"/api/method/{fixture}", None),
			("/api/v2/method/platform_core.identity.tests.mobile_stub.v1_whoami", None),
			("/desk", fixture),
		):
			with self.subTest(path=path, command=command), self.assertRaises(frappe.PermissionError):
				self.check_request(path, command=command, developer_mode=0, allow_tests=0)

	def test_each_opt_in_only_enables_its_own_tools(self):
		fixture = "/api/method/mobile_test_app.fixture.commit_probe"
		self.check_request("/desk/system-console", developer_mode=1)
		self.check_request(fixture, allow_tests=True)
		with self.assertRaises(frappe.PermissionError):
			self.check_request(fixture, developer_mode=1)
		with self.assertRaises(frappe.PermissionError):
			self.check_request("/desk/system-console", allow_tests=True)

	def test_normal_operations_remain_available(self):
		self.check_request("/panel")
		self.check_request("/api/method/platform_core.api.model.test_api")
