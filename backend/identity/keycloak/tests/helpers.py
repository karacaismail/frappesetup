"""Test yardımcıları. Yalnız Python'un kendi kitaplığını kullanır."""

from __future__ import annotations

import base64
import http.client
import json
import os
import urllib.parse
from contextlib import closing
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1]
REALM_FILE = DIRECTORY / "realm" / "platform-realm.json"
USER_FILE = DIRECTORY / "realm" / "dev-users" / "platform-users-0.json"
PASSWORD_LIST = DIRECTORY / "realm" / "password-blacklists" / "common-passwords.txt"
EXAMPLE_ENV = DIRECTORY / ".env.example"


def read_realm() -> dict:
    with REALM_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def read_users() -> dict:
    with USER_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def get_environment_value(name: str) -> str:
    environment_value = os.environ.get(name, "")
    if not environment_value:
        raise KeyError(f"{name} ortam değişkeni boş. Testi bin/kc-dev.sh test ile çalıştırın.")
    return environment_value


def live_available() -> bool:
    return bool(os.environ.get("KC_PUBLIC_URL"))


class HttpResponse:
    def __init__(self, status: int, body: bytes, headers: dict):
        self.status = status
        self.body = body
        self.headers = headers

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except ValueError:
            raise ValueError(safe_detail(self)) from None


def safe_detail(response: "HttpResponse") -> str:
    """Status and OAuth error code of a response, for test failure messages.

    Never the body: a token endpoint that wrongly accepts a request returns tokens in it.
    """
    detail = f"HTTP {response.status}"
    try:
        error = json.loads(response.body.decode("utf-8")).get("error")
    except (ValueError, AttributeError):
        return detail
    if error in (
        "access_denied", "invalid_client", "invalid_grant", "invalid_request", "invalid_scope",
        "invalid_token", "unauthorized_client", "unsupported_grant_type",
    ):
        detail += f" {error}"
    return detail


def assert_refused_without_pkce(test, response: HttpResponse) -> None:
    detail = safe_detail(response)
    location = response.headers.get("Location", "")
    test.assertFalse(b'name="username"' in response.body, detail)
    test.assertFalse("code=" in location, detail)
    if response.status in (302, 303):
        test.assertTrue("error=invalid_request" in location, detail)
    else:
        test.assertEqual(response.status, 400, detail)


def local_test_authority(url, *, allow_mailpit=False):
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise ValueError("Expected a local test URL")
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    port = parts.port
    if (
        parts.scheme != "http" or host not in {"127.0.0.1", "localhost", "identity.localhost"}
        or not port or parts.netloc.lower() != f"{host}:{port}" or parts.fragment
    ):
        raise ValueError("Expected an HTTP URL for a local test service")
    if str(port) == os.environ.get("KC_PORT"):
        return parts
    if host != "identity.localhost":
        if str(port) == os.environ.get("PROD_KC_PORT"):
            return parts
        if allow_mailpit and parts.path.startswith("/api/v1/") and str(port) == os.environ.get("MAILPIT_UI_PORT"):
            return parts
    raise ValueError("Unexpected port for the local test service")


def request(method: str, address: str, *, form: dict | None = None, body: dict | None = None,
          token: str | None = None, headers: dict | None = None) -> HttpResponse:
    parts = local_test_authority(
        address, allow_mailpit=form is None and body is None and token is None and not headers,
    )
    request_body = None
    request_headers = dict(headers or {})
    if any(key.lower() == "host" for key in request_headers):
        raise ValueError("The local test client sets the Host header")
    request_headers["Host"] = parts.netloc
    if form is not None:
        request_body = urllib.parse.urlencode(form).encode("ascii")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        request_body = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    target = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
    # Connect to the literal loopback address. The fixed Keycloak alias is only an HTTP Host value.
    # http.client uses neither proxies nor redirects.
    with closing(http.client.HTTPConnection("127.0.0.1", parts.port, timeout=30)) as connection:
        connection.request(method, target, body=request_body, headers=request_headers)
        with connection.getresponse() as response:
            return HttpResponse(response.status, response.read(), dict(response.getheaders()))


def token_endpoint(realm: str = "platform") -> str:
    return f"{get_environment_value('KC_PUBLIC_URL')}/realms/{realm}/protocol/openid-connect/token"


def client_token(client: str, secret: str, scope: str | None = None) -> HttpResponse:
    form = {"grant_type": "client_credentials", "client_id": client, "client_secret": secret}
    if scope is not None:
        form["scope"] = scope
    return request("POST", token_endpoint(), form=form)


def admin_token() -> str:
    response = request(
        "POST",
        token_endpoint("master"),
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": get_environment_value("KC_BOOTSTRAP_ADMIN_USERNAME"),
            "password": get_environment_value("KC_BOOTSTRAP_ADMIN_PASSWORD"),
        },
    )
    if response.status != 200:
        raise RuntimeError(f"Yönetici belirteci alınamadı: {response.status}")
    return response.json()["access_token"]


def admin(path: str, token: str, method: str = "GET", body: dict | None = None) -> HttpResponse:
    return request(method, f"{get_environment_value('KC_PUBLIC_URL')}/admin/realms/platform{path}", token=token, body=body)


def get_without_redirect(address: str) -> HttpResponse:
    """GET that does not follow redirects, so the Location header can be inspected."""

    return request("GET", address)


def pkce_pair() -> tuple:
    """Returns (code_verifier, code_challenge) for S256 (RFC 7636)."""
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def tenant_authorize_with_pkce(state: str = "test-state", nonce: str = "test-nonce") -> tuple:
    """Returns (authorize_url, code_verifier) for the tenant client with a fresh S256 challenge."""
    verifier, challenge = pkce_pair()
    query = urllib.parse.urlencode(
        {
            "client_id": "site-tenant1",
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": tenant_callback_url(),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{query}", verifier


def tenant_callback_url() -> str:
    return f"{get_environment_value('ATONOTA_SITE_TENANT1_URL')}/api/method/platform_core.api.auth.keycloak_callback"


def tenant_authorize_url(state: str = "test-state", nonce: str = "test-nonce") -> str:
    """Authorize URL for the tenant client with the contract's callback and a fresh S256 challenge."""
    _, challenge = pkce_pair()
    query = urllib.parse.urlencode(
        {
            "client_id": "site-tenant1",
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": f"{get_environment_value('ATONOTA_SITE_TENANT1_URL')}/api/method/platform_core.api.auth.keycloak_callback",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{get_environment_value('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{query}"


def jwt_payload(jwt: str) -> dict:
    chunks = jwt.split(".")
    if len(chunks) != 3:
        raise ValueError("Belirteç üç parçalı değil")
    body = chunks[1] + "=" * (-len(chunks[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(body).decode("utf-8"))
