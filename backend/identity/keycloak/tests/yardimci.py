"""Test yardımcıları. Yalnız Python'un kendi kitaplığını kullanır."""

from __future__ import annotations

import base64
import http.client
import json
import os
import urllib.parse
from contextlib import closing
from pathlib import Path

KLASOR = Path(__file__).resolve().parents[1]
REALM_DOSYASI = KLASOR / "realm" / "platform-realm.json"
KULLANICI_DOSYASI = KLASOR / "realm" / "dev-users" / "platform-users-0.json"
PAROLA_LISTESI = KLASOR / "realm" / "password-blacklists" / "yaygin-parolalar.txt"
ORNEK_ENV = KLASOR / ".env.example"


def realm_oku() -> dict:
    with REALM_DOSYASI.open(encoding="utf-8") as dosya:
        return json.load(dosya)


def kullanicilari_oku() -> dict:
    with KULLANICI_DOSYASI.open(encoding="utf-8") as dosya:
        return json.load(dosya)


def ortam(ad: str) -> str:
    deger = os.environ.get(ad, "")
    if not deger:
        raise KeyError(f"{ad} ortam değişkeni boş. Testi bin/kc-dev.sh test ile çalıştırın.")
    return deger


def canli_var_mi() -> bool:
    return bool(os.environ.get("KC_PUBLIC_URL"))


class HttpYanit:
    def __init__(self, durum: int, govde: bytes, basliklar: dict):
        self.durum = durum
        self.govde = govde
        self.basliklar = basliklar

    def json(self):
        try:
            return json.loads(self.govde.decode("utf-8"))
        except ValueError:
            raise ValueError(safe_detail(self)) from None


def safe_detail(response: "HttpYanit") -> str:
    """Status and OAuth error code of a response, for test failure messages.

    Never the body: a token endpoint that wrongly accepts a request returns tokens in it.
    """
    detail = f"HTTP {response.durum}"
    try:
        error = json.loads(response.govde.decode("utf-8")).get("error")
    except (ValueError, AttributeError):
        return detail
    if error in (
        "access_denied", "invalid_client", "invalid_grant", "invalid_request", "invalid_scope",
        "invalid_token", "unauthorized_client", "unsupported_grant_type",
    ):
        detail += f" {error}"
    return detail


def assert_refused_without_pkce(test, response: HttpYanit) -> None:
    detail = safe_detail(response)
    location = response.basliklar.get("Location", "")
    test.assertFalse(b'name="username"' in response.govde, detail)
    test.assertFalse("code=" in location, detail)
    if response.durum in (302, 303):
        test.assertTrue("error=invalid_request" in location, detail)
    else:
        test.assertEqual(response.durum, 400, detail)


def local_test_authority(url, *, allow_mailpit=False):
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise ValueError("Expected a local test URL")
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    port = parts.port
    if (
        parts.scheme != "http" or host not in {"127.0.0.1", "localhost", "kimlik.localhost"}
        or not port or parts.netloc.lower() != f"{host}:{port}" or parts.fragment
    ):
        raise ValueError("Expected an HTTP URL for a local test service")
    if str(port) == os.environ.get("KC_PORT"):
        return parts
    if host != "kimlik.localhost":
        if str(port) == os.environ.get("PROD_KC_PORT"):
            return parts
        if allow_mailpit and parts.path.startswith("/api/v1/") and str(port) == os.environ.get("MAILPIT_UI_PORT"):
            return parts
    raise ValueError("Unexpected port for the local test service")


def istek(yontem: str, adres: str, *, form: dict | None = None, govde: dict | None = None,
          belirtec: str | None = None, basliklar: dict | None = None) -> HttpYanit:
    parts = local_test_authority(
        adres, allow_mailpit=form is None and govde is None and belirtec is None and not basliklar,
    )
    veri = None
    ust = dict(basliklar or {})
    if any(key.lower() == "host" for key in ust):
        raise ValueError("The local test client sets the Host header")
    ust["Host"] = parts.netloc
    if form is not None:
        veri = urllib.parse.urlencode(form).encode("ascii")
        ust["Content-Type"] = "application/x-www-form-urlencoded"
    elif govde is not None:
        veri = json.dumps(govde).encode("utf-8")
        ust["Content-Type"] = "application/json"
    if belirtec:
        ust["Authorization"] = f"Bearer {belirtec}"
    target = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
    # Connect to the literal loopback address. The fixed Keycloak alias is only an HTTP Host value.
    # http.client uses neither proxies nor redirects.
    with closing(http.client.HTTPConnection("127.0.0.1", parts.port, timeout=30)) as connection:
        connection.request(yontem, target, body=veri, headers=ust)
        with connection.getresponse() as yanit:
            return HttpYanit(yanit.status, yanit.read(), dict(yanit.getheaders()))


def belirtec_ucu(realm: str = "platform") -> str:
    return f"{ortam('KC_PUBLIC_URL')}/realms/{realm}/protocol/openid-connect/token"


def istemci_belirteci(istemci: str, sir: str, kapsam: str | None = None) -> HttpYanit:
    form = {"grant_type": "client_credentials", "client_id": istemci, "client_secret": sir}
    if kapsam is not None:
        form["scope"] = kapsam
    return istek("POST", belirtec_ucu(), form=form)


def yonetici_belirteci() -> str:
    yanit = istek(
        "POST",
        belirtec_ucu("master"),
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ortam("KC_BOOTSTRAP_ADMIN_USERNAME"),
            "password": ortam("KC_BOOTSTRAP_ADMIN_PASSWORD"),
        },
    )
    if yanit.durum != 200:
        raise RuntimeError(f"Yönetici belirteci alınamadı: {yanit.durum}")
    return yanit.json()["access_token"]


def admin(yol: str, belirtec: str, yontem: str = "GET", govde: dict | None = None) -> HttpYanit:
    return istek(yontem, f"{ortam('KC_PUBLIC_URL')}/admin/realms/platform{yol}", belirtec=belirtec, govde=govde)


def get_without_redirect(adres: str) -> HttpYanit:
    """GET that does not follow redirects, so the Location header can be inspected."""

    return istek("GET", adres)


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
    sorgu = urllib.parse.urlencode(
        {
            "client_id": "site-kiraci1",
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": tenant_callback_url(),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{ortam('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{sorgu}", verifier


def tenant_callback_url() -> str:
    return f"{ortam('ATONOTA_SITE_KIRACI1_URL')}/api/method/platform_core.api.auth.keycloak_callback"


def tenant_authorize_url(state: str = "test-state", nonce: str = "test-nonce") -> str:
    """Authorize URL for the tenant client with the contract's callback and a fresh S256 challenge."""
    _, challenge = pkce_pair()
    sorgu = urllib.parse.urlencode(
        {
            "client_id": "site-kiraci1",
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": f"{ortam('ATONOTA_SITE_KIRACI1_URL')}/api/method/platform_core.api.auth.keycloak_callback",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{ortam('KC_PUBLIC_URL')}/realms/platform/protocol/openid-connect/auth?{sorgu}"


def jwt_govdesi(jwt: str) -> dict:
    parcalar = jwt.split(".")
    if len(parcalar) != 3:
        raise ValueError("Belirteç üç parçalı değil")
    govde = parcalar[1] + "=" * (-len(parcalar[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(govde).decode("utf-8"))
