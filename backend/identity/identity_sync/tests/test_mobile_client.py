"""The platform_core mobile client against this service, over real HTTP.

The client lives in another job's folder (`apps/platform_core/.../mobil/identity_sync_client.py`).
It gets its service token from `kimlik/service_client.py`. This test loads both files read-only
and lets them call the real server of this service. Only two things are replaced: the `frappe`
module (the client reads settings and a logger from it) and the two "https only" address checks,
because the test servers speak plain HTTP on 127.0.0.1. The token request, the client id check,
the request body and the headers are the client's own.
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
SERVICE_CLIENT = CLIENT.parents[1] / "kimlik" / "service_client.py"
SID = "55555555-5555-4555-8555-555555555555"
OTHER_USER = "99999999-9999-4999-8999-999999999999"
OTHER_SID = "66666666-6666-4666-8666-666666666666"


@unittest.skipUnless(
    CLIENT.is_file() and SERVICE_CLIENT.is_file(), "the platform_core mobile client is not in this checkout"
)
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
            if form.get("client_id") != ["site-kiraci1-service"]:
                return keycloak._token(req)  # the service's own admin token
            self.token_forms.append(form)
            return 200, {"access_token": SESSION_TOKEN, "expires_in": 300, "token_type": "Bearer"}

        keycloak.on("POST", token_path, token)
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.client = self.load_client(
            {
                "mobile_identity_sync_url": f"http://127.0.0.1:{self.httpd.server_address[1]}",
                "test_token_url": keycloak.url + token_path,
                # docs/sozlesmeler.md, section 8: the site's browser client and its service client.
                "keycloak_client_id": "site-kiraci1",
                "keycloak_service_client_id": "site-kiraci1-service",
                "keycloak_service_client_secret": "made-up-site-value",
            }
        )

    def load_client(self, conf: dict[str, str]) -> types.ModuleType:
        """Load the client and the token module it imports, without Frappe.

        The two files are loaded by path under their real module names. `frappe` and the two
        parent packages are stand-ins, removed again after loading.
        """
        frappe = types.ModuleType("frappe")
        frappe.conf = conf
        frappe.logger = lambda _name: types.SimpleNamespace(warning=self.warnings.append, error=self.errors.append)
        names = ("frappe", "platform_core", "platform_core.kimlik", "platform_core.kimlik.service_client")
        previous = {name: sys.modules.get(name) for name in names}
        sys.modules["frappe"] = frappe
        sys.modules["platform_core"] = types.ModuleType("platform_core")
        sys.modules["platform_core.kimlik"] = types.ModuleType("platform_core.kimlik")
        try:
            tokens = self.load_file("platform_core.kimlik.service_client", SERVICE_CLIENT)
            sys.modules["platform_core.kimlik.service_client"] = tokens
            module = self.load_file("mobile_identity_sync_client_under_test", CLIENT)
        finally:
            for name, value in previous.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
        # The two "https only" address checks are replaced: the test servers speak plain HTTP
        # on 127.0.0.1. Everything else is the client's own code, the client id check included.
        token_url = conf["test_token_url"]
        service_url = conf["mobile_identity_sync_url"]
        assert urlsplit(token_url).hostname == urlsplit(service_url).hostname == "127.0.0.1"
        tokens._token_url = lambda: token_url
        module._identity_sync_origin = lambda: service_url.rstrip("/")
        return module

    @staticmethod
    def load_file(name: str, path: pathlib.Path) -> types.ModuleType:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
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
        self.assertEqual((self.warnings, self.errors), ([], []))

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

    def test_refusal_for_another_tenants_user_is_logged_and_the_allowed_session_ends(self) -> None:
        # The site names a user who is not a member of its organization. The service answers 403.
        # The client logs the refusal and does not retry it. Its own user's session still ends.
        statuses: list[int] = []
        original = self.httpd.RequestHandlerClass.send_response

        def record(handler, code, message=None):
            statuses.append(code)
            return original(handler, code, message)

        self.httpd.RequestHandlerClass.send_response = record
        self.addCleanup(setattr, self.httpd.RequestHandlerClass, "send_response", original)

        failed = self.client.send_session_revocations([(OTHER_SID, OTHER_USER), (SID, SUBJECT)])

        self.assertEqual(statuses, [403, 200])
        self.assertEqual(failed, ())
        self.assertEqual(self.stack.keycloak.sessions[OTHER_USER], [OTHER_SID])
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [])
        self.assertEqual(len(self.errors), 1)
        self.assertIn("403", self.errors[0])
        self.assertEqual(self.warnings, [])

    def test_unreachable_service_is_reported_as_failed(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

        failed = self.client.send_session_revocations([(SID, SUBJECT)])

        self.assertEqual(failed, ((SID, SUBJECT),))
        self.assertEqual(self.stack.keycloak.sessions[SUBJECT], [SID])
        self.assertEqual(len(self.warnings), 1)
