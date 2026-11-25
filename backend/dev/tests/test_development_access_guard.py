"""G-40: tenant sites refuse development endpoints without Frappe or a site.

The app test in `platform_core/tests/test_development_access.py` needs a Frappe test site.
This test loads the same guard with a stand-in `frappe` module, so the local gate runs it.
"""

import ast
import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2] / "apps" / "platform_core"
HOOKS = APP / "platform_core" / "hooks.py"
GUARD = "platform_core.development_access.guard_development_endpoints"
CONSOLE = "frappe.desk.doctype.system_console.system_console"
FIXTURE = "mobile_test_app.fixture.commit_probe"


class Refused(Exception):
    pass


def hook_list(name):
    for node in ast.parse(HOOKS.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return []


class DevelopmentAccessGuardTests(unittest.TestCase):
    def check(self, path, *, command=None, **config):
        fake = SimpleNamespace(
            local=SimpleNamespace(request=SimpleNamespace(path=path)),
            form_dict={"cmd": command},
            conf=config,
            PermissionError=Refused,
            _=lambda text: text,
        )

        def throw(message, exc=Exception):
            raise exc(message)

        fake.throw = throw
        with patch.object(sys, "path", [str(APP), *sys.path]), patch.dict(sys.modules, {"frappe": fake}):
            sys.modules.pop("platform_core.development_access", None)
            module = importlib.import_module("platform_core.development_access")
            try:
                module.guard_development_endpoints()
            finally:
                sys.modules.pop("platform_core.development_access", None)

    def test_guard_runs_first_in_before_request(self):
        # Later request hooks may answer the request, so the guard must run before them.
        self.assertEqual(hook_list("before_request")[:1], [GUARD])
        self.assertEqual(hook_list("before_request").count(GUARD), 1)

    def test_console_and_test_endpoints_are_refused_when_switches_are_off(self):
        for path, command in (
            ("/app/system-console", None),
            ("/desk/system-console/", None),
            (f"/api/method/{CONSOLE}.execute_code", None),
            (f"/api/v1/method/{CONSOLE}.show_processlist", None),
            (f"/api/v2/method/{CONSOLE}.execute_code", None),
            ("/", f"{CONSOLE}.execute_code"),
            (f"/api/method/{FIXTURE}", None),
            ("/api/method/platform_core.identity.tests.mobile_stub.v1_whoami", None),
            ("/", FIXTURE),
        ):
            for config in ({}, {"developer_mode": 0, "allow_tests": 0}, {"developer_mode": "0"}):
                with self.subTest(path=path, command=command, config=config), self.assertRaises(Refused):
                    self.check(path, command=command, **config)

    def test_each_switch_opens_only_its_own_tool(self):
        self.check("/desk/system-console", developer_mode=1)
        self.check(f"/api/method/{FIXTURE}", allow_tests=1)
        with self.assertRaises(Refused):
            self.check(f"/api/method/{FIXTURE}", developer_mode=1)
        with self.assertRaises(Refused):
            self.check("/desk/system-console", allow_tests=1)

    def test_normal_requests_pass(self):
        self.check("/panel")
        self.check("/api/method/platform_core.api.model.test_api")
        self.check("/api/method/frappe.auth.get_logged_user", command="frappe.auth.get_logged_user")


if __name__ == "__main__":
    unittest.main()
