"""Exercise bearer-authenticated Website Users with the real shell gate."""

from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from platform_core.api import mobile
from platform_core.mobil.tests.test_service import RECORD, SampleCommand

from .fixture import WEBSITE


class WebsiteMobileTest(IntegrationTestCase):
    def setUp(self):
        self.site = frappe.local.site
        self.client = get_test_client(use_cookies=False)
        self.assertEqual(frappe.db.get_value("User", WEBSITE, "user_type"), "Website User")
        hooks = frappe.get_hooks("auth_hooks")
        self.assertLess(
            hooks.index("mobile_test_app.fixture.authenticate"),
            hooks.index("platform_core.kabuk.native_metadata.guard_native_metadata"),
        )
        override = frappe.override_whitelisted_method

        def use_production_mobile_methods(method):
            if method.startswith("platform_core.api.mobile."):
                return method
            return override(method)

        # The load fixture overrides two methods. Exercise the original RPC targets here.
        self.enterContext(patch.object(frappe, "override_whitelisted_method", use_production_mobile_methods))

    def post(self, endpoint, body, sid, caller=None):
        headers = {
            "Authorization": "Bearer fixture-website",
            "X-Mobile-App-Version": "1.0.0",
            "X-Mobile-Contract-Version": "1",
            "X-Mobile-Test-Sid": sid,
        }
        if caller is not None:
            headers["X-Mobile-Test-Installation"] = caller
        return make_request(
            self.client.open,
            args=(),
            kwargs={
                "path": f"/api/method/platform_core.api.mobile.{endpoint}",
                "method": "POST",
                "json": body,
                "headers": headers,
            },
            site=self.site,
        )

    def expect_success(self, endpoint, body, sid, caller=None):
        response = self.post(endpoint, body, sid, caller)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json["message"]

    def test_website_user_can_call_all_seven_mobile_methods(self):
        sid, second_sid = str(uuid4()), str(uuid4())
        installation = str(uuid4())
        current = {"installation_id": installation}
        other = {"installation_id": str(uuid4())}
        self.assertEqual(self.expect_success("v1_register", current, sid), current)
        self.assertEqual(self.expect_success("v1_register", other, second_sid), other)
        self.assertIn("last_user_activity_at", self.expect_success("v1_activity", current, sid))
        self.assertIn("changes", self.expect_success("v1_pull", current, sid))
        operation = {
            "operation_id": str(uuid4()),
            "command": "sample.update",
            "record_id": RECORD,
            "version": "1",
            "fields": {"title": "Sample"},
        }
        with patch.object(mobile, "COMMANDS", {"sample.update": SampleCommand()}):
            pushed = self.expect_success("v1_push", dict(current, operations=[operation]), sid)
        self.assertEqual(
            pushed["operations"], [{"operation_id": operation["operation_id"], "status": "applied"}]
        )
        listed = self.expect_success("v1_list_installations", {}, sid, caller=installation)
        self.assertIn(installation, [item["installation_id"] for item in listed["installations"]])
        self.assertEqual(
            self.expect_success("v1_revoke_installation", other, sid, caller=installation), {"revoked": 1}
        )
        self.assertEqual(self.expect_success("v1_revoke", current, sid), {"revoked": 1})

    def test_website_user_cannot_call_mobile_cleanup(self):
        response = self.post("v1_cleanup", {"dry_run": True}, str(uuid4()))
        self.assertEqual(response.status_code, 403, response.get_data(as_text=True))
        self.assertNotEqual(response.json.get("code"), "cleanup_forbidden")
