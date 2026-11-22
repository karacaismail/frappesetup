"""The platform_core mobile client against this service, over real HTTP.

The client lives in another job's folder (`apps/platform_core/.../mobil/identity_sync_client.py`).
This test loads it read-only and lets it call the real server of this service. Only two things
are replaced: the `frappe` module (the client reads three settings and a logger from it) and the
client's "https only" address check, because the test server speaks plain HTTP on 127.0.0.1.
The token request, the request body and the headers are the client's own.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from urllib.parse import urlsplit

from . import fakes
from .fakes import SUBJECT, keycloak_user
from .test_server import SESSION_TOKEN, ServerCase

CLIENT = (
    pathlib.Path(__file__).resolve().parents[3]
    / "apps"
    / "platform_core"
    / "platform_core"
    / "mobil"
    / "identity_sync_client.py"
)
SID = "55555555-5555-4555-8555-555555555555"
OTHER_USER = "99999999-9999-4999-8999-999999999999"
OTHER_SID = "66666666-6666-4666-8666-666666666666"


@unittest.skipUnless(CLIENT.is_file(), "the platform_core mobile client is not in this checkout")
class MobileClientTest(ServerCase):
    two_tenants = True

    def setUp(self) -> None:
        super().setUp()
        keycloak = self.stack.keycloak
        other_org = {"id": "o-kiraci2", "name": "kiraci2", "alias": "kiraci2"}
        keycloak.add_user(keycloak_user(subject=OTHER_USER, email="ikinci@example.test"), [other_org])
        keycloak.add_session(SUBJECT, SID)
        keycloak.add_session(OTHER_USER, OTHER_SID)
        token_path = f"/realms/{fakes.ISSUER_REALM}/protocol/openid-connect/token"
        self.token_forms: list[dict[str, list[str]]] = []

        def token(req: fakes.Recorded) -> fakes.Reply:
            form = req.form()
            if form.get("client_id") != ["site-kiraci1"]:
                return keycloak._token(req)  # the service's own admin token
            self.token_forms.append(form)
            return 200, {"access_token": SESSION_TOKEN, "expires_in": 300, "token_type": "Bearer"}

        keycloak.on("POST", token_path, token)
        self.warnings: list[str] = []
        self.client = self.load_client(
            {
                "mobile_identity_sync_url": f"http://127.0.0.1:{self.httpd.server_address[1]}",
                "mobile_identity_sync_token_url": keycloak.url + token_path,
                "mobile_identity_sync_client_id": "site-kiraci1",
                "mobile_identity_sync_client_secret": "made-up-site-secret",
            }
        )

    def load_client(self, conf: dict[str, str]) -> types.ModuleType:
        frappe = types.ModuleType("frappe")
        frappe.conf = conf
        frappe.logger = lambda _name: types.SimpleNamespace(warning=self.warnings.append)
        previous = sys.modules.get("frappe")
        sys.modules["frappe"] = frappe
        try:
            spec = importlib.util.spec_from_file_location("mobile_identity_sync_client_under_test", CLIENT)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            if previous is None:
                del sys.modules["frappe"]
            else:
                sys.modules["frappe"] = previous

        def plain_http_url(key: str, *, origin_only: bool = False) -> str:
            value = conf[key]
            assert urlsplit(value).hostname == "127.0.0.1"
            return value.rstrip("/") if origin_only else value

        module._configured_url = plain_http_url
        return module

    def test_client_request_ends_the_session(self) -> None:
        failed = self.client.send_session_revocations([(SID, SUBJECT)])

        self.assertEqual(failed, ())
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [])
        self.assertEqual(self.stack.keycloak.sessions[OTHER_USER], [OTHER_SID])
        (form,) = self.token_forms
        # docs/sozlesmeler.md, section 7: the site asks for the token with this scope.
        self.assertEqual(form["scope"], ["aud-identity-sync"])
        self.assertEqual(form["grant_type"], ["client_credentials"])
        self.assertEqual(self.warnings, [])

    def test_client_request_body_matches_the_contract(self) -> None:
        from .test_contract import CONTRACT, request_schema, schema_errors

        sent: list[object] = []
        original = self.stack.app.keycloak.list_user_session_ids

        def spy(subject: str) -> tuple[str, ...]:
            sent.append(subject)
            return original(subject)

        self.stack.app.keycloak.list_user_session_ids = spy
        self.client.send_session_revocations([(SID, SUBJECT)])

        self.assertEqual(sent, [SUBJECT])
        schema = request_schema("POST", "/v1/sessions/revoke")
        self.assertEqual(schema_errors({"sid": SID, "subject": SUBJECT}, schema, CONTRACT), [])

    def test_repeat_is_not_a_failure(self) -> None:
        self.assertEqual(self.client.send_session_revocations([(SID, SUBJECT)]), ())

        self.assertEqual(self.client.send_session_revocations([(SID, SUBJECT)]), ())

    def test_user_of_another_tenant_is_reported_as_failed(self) -> None:
        # The site names a user who is not a member of its organization. The service answers 403.
        failed = self.client.send_session_revocations([(OTHER_SID, OTHER_USER), (SID, SUBJECT)])

        self.assertEqual(failed, ((OTHER_SID, OTHER_USER),))
        self.assertEqual(self.stack.keycloak.sessions[OTHER_USER], [OTHER_SID])
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [])
        self.assertEqual(len(self.warnings), 1)
