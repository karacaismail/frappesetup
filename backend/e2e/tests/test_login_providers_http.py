"""The two AtonotA Login reads over real HTTP on a running tenant site (AJA-516).

The test needs a running local stack. It never starts one. Point it at the tenant site:

    FS_TENANT_URL=http://tenant1.localhost:7401 python3 -m unittest backend/e2e/tests/test_login_providers_http.py -v

Without `FS_TENANT_URL` every test is skipped. The test sends only a few requests, so it stays far
below the rate limit of 30 requests per minute. Every request is a guest request: no cookie.
"""

from __future__ import annotations

import json
import os
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = os.environ.get("FS_TENANT_URL", "").rstrip("/")
METHOD = "/api/method/platform_core.api.auth."
PROVIDER_FIELDS = {"alias", "display_name"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(_NoRedirect())


def call(method: str, name: str, *, body: bytes | None = None) -> tuple[int, dict, object]:
    """One guest request. Returns the status, the headers and the decoded JSON body."""
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(BASE + METHOD + name, data=body, headers=headers, method=method)
    try:
        with OPENER.open(request, timeout=10) as response:
            status, header, raw = response.status, dict(response.headers), response.read()
    except HTTPError as error:
        with error:
            status, header, raw = error.code, dict(error.headers), error.read()
    try:
        decoded = json.loads(raw) if raw else None
    except ValueError:
        decoded = raw.decode("utf-8", "replace")
    return status, {key.lower(): value for key, value in header.items()}, decoded


@unittest.skipUnless(BASE, "Set FS_TENANT_URL to a running tenant site, for example http://tenant1.localhost:7401")
class GuestLoginProvidersHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        address = urlsplit(BASE)
        if address.scheme not in ("http", "https") or not address.hostname:
            raise unittest.SkipTest("FS_TENANT_URL must be an http or https address")

    def test_guest_get_gets_200_and_only_the_panel_fields(self):
        status, headers, body = call("GET", "list_login_providers")
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        message = body["message"]
        self.assertEqual(set(message), {"providers"})
        self.assertIsInstance(message["providers"], list)
        for row in message["providers"]:
            with self.subTest(row=row):
                self.assertEqual(set(row), PROVIDER_FIELDS)
        directives = {part.strip() for part in headers.get("cache-control", "").split(",")}
        self.assertIn("no-store", directives)

    def test_guest_reply_carries_no_secret_or_internal_address(self):
        status, _headers, body = call("GET", "list_login_providers")
        self.assertEqual(status, 200, body)
        text = json.dumps(body)
        for leak in ("clientSecret", "config", "identity-sync", "Bearer", "Traceback"):
            self.assertNotIn(leak, text)

    def test_guest_post_is_refused(self):
        status, _headers, body = call("POST", "list_login_providers", body=b"{}")
        self.assertEqual(status, 403, body)

    def test_guest_linked_accounts_stay_closed(self):
        status, _headers, body = call("GET", "list_linked_accounts")
        self.assertEqual(status, 403, body)
        self.assertEqual(body.get("exc_type"), "PermissionError")


if __name__ == "__main__":
    unittest.main()
