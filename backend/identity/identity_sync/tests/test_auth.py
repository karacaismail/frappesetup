"""Servis belirtecinin gerçek doğrulama yolu.

Kurallar `docs/sozlesmeler.md` dosyasının 3. bölümündedir. Doğrulamayı ortak `oidc_verify`
kitaplığı yapar. Bu testler kitaplığı gerçek HTTP girişinden sınar. Anahtarlar testte üretilir.

Kitaplık kurulu değilse gerçek yol testleri atlanır. O koşu `not_run` sayılır.
Kitaplıkla koşmak için komut README dosyasındadır.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

from identity_sync.auth import TokenRejected, build_verifier, reject_all
from identity_sync.server import make_server

from . import fakes
from .fakes import Stack

try:
    import jwt
    # Imported only to learn whether the library is installed.
    import oidc_verify  # noqa: F401
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    HAVE_LIBRARY = False
else:
    HAVE_LIBRARY = True

CERTS_PATH = "/realms/platform/protocol/openid-connect/certs"


class FailClosedTest(unittest.TestCase):
    """Doğrulama kurulamıyorsa servis her isteği reddeder."""

    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)

    def test_missing_library_rejects_everything(self) -> None:
        with mock.patch.dict(sys.modules, {"oidc_verify": None}):
            verifier = build_verifier(self.stack.settings)

        self.assertIs(verifier, reject_all)
        with self.assertRaises(TokenRejected):
            verifier("herhangi-bir-belirtec")

    def test_empty_client_lists_reject_everything(self) -> None:
        import dataclasses

        empty = frozenset()
        settings = dataclasses.replace(
            self.stack.settings, execute_azp=empty, preview_azp=empty, session_azp=empty, deletion_azp=empty
        )

        self.assertIs(build_verifier(settings), reject_all)

    def test_server_with_reject_all_answers_401(self) -> None:
        httpd = make_server(self.stack.app, reject_all, host="127.0.0.1", port=0, request_timeout=0.5)
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        request = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/v1/dead-letters", headers={"Authorization": "Bearer x"}
        )

        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 401)


def _b64(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@unittest.skipUnless(HAVE_LIBRARY, "oidc_verify kitaplığı kurulu değil")
class RealVerificationTest(unittest.TestCase):
    """Gerçek RS256 belirteçleri, gerçek anahtar listesi ve gerçek HTTP girişi."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self) -> None:
        self.stack = Stack()
        self.addCleanup(self.stack.close)
        numbers = self.key.public_key().public_numbers()
        jwks = {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "k1", "n": _b64(numbers.n), "e": _b64(numbers.e)}]}
        self.stack.keycloak.on("GET", CERTS_PATH, (200, jwks))
        httpd = make_server(
            self.stack.app, build_verifier(self.stack.settings), host="127.0.0.1", port=0, request_timeout=2.0
        )
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def token(self, *, key=None, kid: str = "k1", algorithm: str = "RS256", **overrides: object) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": self.stack.issuer,
            "aud": "identity-sync",
            "azp": "site-tenant1-service",
            "sub": "service-account-site-tenant1-service",
            "iat": now,
            "exp": now + 300,
        }
        claims.update(overrides)
        claims = {name: value for name, value in claims.items() if value is not None}
        return jwt.encode(claims, key or self.key, algorithm=algorithm, headers={"kid": kid})

    def status(self, token: str, method: str = "GET", path: str = "/v1/dead-letters", body: bytes | None = None) -> int:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code

    def test_valid_token_is_accepted(self) -> None:
        self.assertEqual(self.status(self.token()), 200)

    def test_token_signed_with_other_key_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(key=self.other_key)), 401)

    def test_wrong_audience_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(aud="site-tenant1")), 401)

    def test_multiple_audiences_are_rejected(self) -> None:
        # Servis belirteci yalnız bir `aud` değeri taşır.
        self.assertEqual(self.status(self.token(aud=["identity-sync", "press"])), 401)

    def test_wrong_issuer_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(iss="http://baska.example.test/realms/platform")), 401)

    def test_unlisted_client_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(azp="stranger-service")), 401)

    def test_missing_azp_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(azp=None)), 401)

    def test_expired_token_is_rejected(self) -> None:
        now = int(time.time())
        self.assertEqual(self.status(self.token(iat=now - 600, exp=now - 300)), 401)

    def test_token_inside_leeway_is_accepted(self) -> None:
        # Saat payı 30 saniyedir.
        now = int(time.time())
        self.assertEqual(self.status(self.token(iat=now - 600, exp=now - 10)), 200)

    def test_missing_exp_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(exp=None)), 401)

    def test_unknown_key_id_is_rejected(self) -> None:
        self.assertEqual(self.status(self.token(kid="bilinmeyen")), 401)

    def test_symmetric_algorithm_is_rejected(self) -> None:
        # Yalnız RS256 kabul edilir.
        forged = jwt.encode(
            {"iss": self.stack.issuer, "aud": "identity-sync", "azp": "site-tenant1-service", "exp": int(time.time()) + 300},
            "x" * 64,
            algorithm="HS256",
            headers={"kid": "k1"},
        )
        self.assertEqual(self.status(forged), 401)

    def test_garbage_token_is_rejected(self) -> None:
        self.assertEqual(self.status("belirtec-degil"), 401)

    def test_jwks_failure_is_a_rejection_not_a_crash(self) -> None:
        self.stack.keycloak.on("GET", CERTS_PATH, (500, None))

        self.assertEqual(self.status(self.token()), 401)

    def test_agent_token_previews_but_cannot_execute(self) -> None:
        agent = self.token(azp="ai-agent")
        execute = json.dumps({"dry_run": False, "preview_digest": "0" * 64, "approval_id": "onay-1"}).encode()

        self.assertEqual(self.status(agent, "POST", "/v1/dead-letters/replay", b'{"dry_run": true}'), 200)
        self.assertEqual(self.status(agent, "POST", "/v1/dead-letters/replay", execute), 403)

    def test_approval_layer_token_may_execute(self) -> None:
        # Kuyruk boş. Boş planın özeti tutmaz ve servis 409 döner. Yetki denetimi geçmiştir.
        execute = json.dumps({"dry_run": False, "preview_digest": "0" * 64, "approval_id": "onay-1"}).encode()

        self.assertEqual(self.status(self.token(), "POST", "/v1/dead-letters/replay", execute), 409)


if __name__ == "__main__":
    unittest.main()
