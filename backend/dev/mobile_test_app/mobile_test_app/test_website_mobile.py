"""Exercise bearer-authenticated Website Users with the real shell gate."""

from time import time
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password
from platform_core.api import mobile
from platform_core.mobile.store import MobileStore
from platform_core.mobile.tests.http_diagnostics import http_diagnostic, safe_http_error_code
from platform_core.mobile.tests.test_service import RECORD, SampleCommand

from .fixture import SERVICE_TARGET, WEBSITE

PHONE_METHODS = (
    "v1_register",
    "v1_activity",
    "v1_push",
    "v1_pull",
    "v1_list_installations",
    "v1_revoke_installation",
    "v1_revoke",
)
CLEANUP = "v1_cleanup"
SERVICE = "revoke_user_installations"
SERVICE_BODY = {"issuer": "fixture", "subject": "fixture-service-target"}
ALL_METHODS = (*PHONE_METHODS, CLEANUP, SERVICE)


class WebsiteMobileTest(IntegrationTestCase):
    def setUp(self):
        self.site = frappe.local.site
        self.client = get_test_client(use_cookies=False)
        self.assertEqual(frappe.db.get_value("User", WEBSITE, "user_type"), "Website User")
        hooks = frappe.get_hooks("auth_hooks")
        self.assertLess(
            hooks.index("mobile_test_app.fixture.authenticate"),
            hooks.index("platform_core.shell.native_metadata.guard_native_metadata"),
        )
        override = frappe.override_whitelisted_method

        def use_production_mobile_methods(method):
            if method.startswith("platform_core.api.mobile."):
                return method
            return override(method)

        # The load fixture overrides two methods. Exercise the original RPC targets here.
        self.enterContext(patch.object(frappe, "override_whitelisted_method", use_production_mobile_methods))

    def request(self, method, body, *, client=None, headers=None):
        client = self.client if client is None else client
        return make_request(
            client.open,
            args=(),
            kwargs={
                "path": f"/api/method/{method}",
                "method": "POST",
                "json": body,
                "headers": headers or {},
            },
            site=self.site,
        )

    def post(self, endpoint, body, sid, caller=None, *, token="fixture-website", extra_headers=None):
        headers = {
            "X-Mobile-App-Version": "1.0.0",
            "X-Mobile-Contract-Version": "1",
            "X-Mobile-Test-Sid": sid,
            **(extra_headers or {}),
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if caller is not None:
            headers["X-Mobile-Test-Installation"] = caller
        return self.request(f"platform_core.api.mobile.{endpoint}", body, headers=headers)

    @staticmethod
    def body_for(endpoint, installation):
        if endpoint == SERVICE:
            return SERVICE_BODY
        if endpoint == CLEANUP:
            return {"dry_run": True}
        if endpoint == "v1_list_installations":
            return {}
        body = {"installation_id": installation}
        if endpoint == "v1_push":
            body["operations"] = [
                {
                    "operation_id": str(uuid4()),
                    "command": "sample.update",
                    "record_id": RECORD,
                    "version": "1",
                    "fields": {"title": "Sample"},
                }
            ]
        return body

    @staticmethod
    def token_for(endpoint):
        return {CLEANUP: "fixture-cleanup", SERVICE: "fixture-service"}.get(endpoint, "fixture-website")

    def assert_status(self, response, expected, *, code=None):
        self.assertEqual(
            response.status_code,
            expected,
            http_diagnostic(response.status_code, response.get_json(silent=True)),
        )
        if code:
            self.assertEqual(safe_http_error_code(response.get_json(silent=True)), code)

    def test_matrix_covers_every_whitelisted_mobile_method(self):
        methods = {
            handler.__name__ for handler in frappe.whitelisted if handler.__module__ == mobile.__name__
        }
        self.assertEqual(methods, set(ALL_METHODS))

    def test_every_mobile_method_denies_a_guest(self):
        installation, sid = str(uuid4()), str(uuid4())
        for endpoint in ALL_METHODS:
            with self.subTest(endpoint=endpoint):
                self.assert_status(
                    self.post(endpoint, self.body_for(endpoint, installation), sid, token=None), 403
                )

    def test_every_mobile_method_denies_a_cookie_without_a_bearer(self):
        password = uuid4().hex
        update_password(WEBSITE, password)
        # Frappe's HTTP test client uses a separate database connection.
        frappe.db.commit()  # nosemgrep: frappe-request-commit
        client = get_test_client(use_cookies=True)
        login = self.request("login", {"usr": WEBSITE, "pwd": password}, client=client)
        self.assert_status(login, 200)
        sid = client.get_cookie("sid").value
        self.addCleanup(frappe.cache.hdel, "session", sid)
        session = frappe.cache.hget("session", sid)
        session["data"]["csrf_token"] = frappe.generate_hash()
        frappe.cache.hset("session", sid, session)
        headers = {"X-Frappe-CSRF-Token": session["data"]["csrf_token"]}
        installation = str(uuid4())
        for endpoint in ALL_METHODS:
            with self.subTest(endpoint=endpoint):
                response = self.request(
                    f"platform_core.api.mobile.{endpoint}",
                    self.body_for(endpoint, installation),
                    client=client,
                    headers=headers,
                )
                if endpoint in PHONE_METHODS:
                    self.assert_status(response, 401, code="mobile_token_required")
                else:
                    self.assert_status(response, 403)

    def test_every_mobile_method_denies_a_token_from_another_site(self):
        with patch.object(mobile, "_linked_account", return_value=SERVICE_TARGET):
            self.assert_denied_claims(
                {"X-Mobile-Test-Identity-Mismatch": "site"}, mobile_error="mobile_token_required"
            )

    def test_every_mobile_method_denies_an_expired_token(self):
        with patch.object(mobile, "_linked_account", return_value=SERVICE_TARGET):
            self.assert_denied_claims({"X-Mobile-Test-Expires": str(int(time()) - 60)})

    def assert_denied_claims(self, headers, *, mobile_error=None):
        installation, sid = str(uuid4()), str(uuid4())
        for endpoint in ALL_METHODS:
            with self.subTest(endpoint=endpoint):
                response = self.post(
                    endpoint,
                    self.body_for(endpoint, installation),
                    sid,
                    caller=installation,
                    token=self.token_for(endpoint),
                    extra_headers=headers,
                )
                self.assert_status(response, 401, code=mobile_error if endpoint != SERVICE else None)
                if mobile_error is None or endpoint == SERVICE:
                    self.assertEqual(response.json.get("exc_type"), "AuthenticationError")

    def test_every_mobile_method_denies_a_revoked_phone(self):
        installation, sid = str(uuid4()), str(uuid4())
        self.expect_success("v1_register", {"installation_id": installation}, sid)
        # The HTTP request committed on a different connection. End the test's earlier read snapshot.
        frappe.db.rollback()
        MobileStore().revoke_targets((installation,), remote=False)
        # Make the local denial visible to the WSGI requests.
        frappe.db.commit()  # nosemgrep: frappe-request-commit
        for endpoint in ALL_METHODS:
            with self.subTest(endpoint=endpoint):
                token = self.token_for(endpoint) if endpoint != SERVICE else "fixture-website"
                response = self.post(
                    endpoint,
                    self.body_for(endpoint, installation),
                    sid,
                    caller=installation,
                    token=token,
                )
                self.assert_status(
                    response, 401, code="mobile_session_revoked" if endpoint != SERVICE else None
                )

    def test_admin_bearer_can_call_cleanup(self):
        response = self.post(CLEANUP, {"dry_run": True}, str(uuid4()), token="fixture-cleanup")
        self.assert_status(response, 200)
        self.assertTrue(response.json["message"]["dry_run"])

    def test_identity_sync_bearer_can_call_service_revocation(self):
        with patch.object(mobile, "_linked_account", return_value=SERVICE_TARGET):
            response = self.post(SERVICE, SERVICE_BODY, str(uuid4()), token="fixture-service")
        self.assert_status(response, 200)
        self.assertIn("revoked", response.json["message"])

    def expect_success(self, endpoint, body, sid, caller=None):
        response = self.post(endpoint, body, sid, caller)
        self.assertEqual(
            response.status_code, 200, http_diagnostic(response.status_code, response.get_json(silent=True))
        )
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
        self.assertEqual(
            response.status_code, 403, http_diagnostic(response.status_code, response.get_json(silent=True))
        )
        self.assertNotEqual(safe_http_error_code(response.get_json(silent=True)), "cleanup_forbidden")
