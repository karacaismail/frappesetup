"""Regression tests for the security review findings (token typing, logout claims, JWKS cache, time claims).

Keys are generated locally. The JWKS cache is fed by a fake fetcher or by a loopback HTTP server.
"""

import base64
import http.server
import json
import threading
import time
import unittest
from urllib.error import URLError

from anahtarlar import ISSUER, LOGOUT_EVENT, Anahtar, SahteJwks, cikis_govdesi, erisim_govdesi, kimlik_govdesi
from jwt.algorithms import RSAAlgorithm

from oidc_verify import (
    JwksCache,
    JwksUnavailable,
    TokenError,
    verify_access_token,
    verify_id_token,
    verify_logout_token,
)

JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_raw(key: Anahtar, payload: dict) -> str:
    """Builds and signs a JWT without PyJWT's encoder, so any JSON payload can be produced.

    `None` values stay in the payload as JSON null. Non-finite floats are written as JSON Infinity.
    """
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": key.kid}).encode("utf-8"))
    body = _b64url(json.dumps(payload).encode("utf-8"))
    algorithm = RSAAlgorithm(RSAAlgorithm.SHA256)
    signature = algorithm.sign(f"{header}.{body}".encode("ascii"), algorithm.prepare_key(key.ozel_pem))
    return f"{header}.{body}.{_b64url(signature)}"


class VerifierBase(unittest.TestCase):
    def setUp(self):
        self.key = Anahtar("kid-1")
        self.fetcher = SahteJwks(self.key)
        self.cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=self.fetcher)

    def access(self, token, **override):
        options = {
            "cache": self.cache,
            "issuer": ISSUER,
            "audience": "site-kiraci1",
            "allowed_azp": {"identity-sync"},
            "leeway": 30,
        }
        options.update(override)
        return verify_access_token(token, **options)

    def identity(self, token, **override):
        options = {
            "cache": self.cache,
            "issuer": ISSUER,
            "client_id": "press",
            "nonce": "n-123",
            "leeway": 30,
        }
        options.update(override)
        return verify_id_token(token, **options)

    def logout(self, token, **override):
        options = {"cache": self.cache, "issuer": ISSUER, "client_id": "press", "leeway": 30}
        options.update(override)
        return verify_logout_token(token, **options)

    def error_code(self, func, *args, **kwargs) -> str:
        with self.assertRaises(TokenError) as caught:
            func(*args, **kwargs)
        return caught.exception.code


class TokenTypeConfusionTest(VerifierBase):
    """O1: a token minted for one verifier must not pass another one (RFC 8725 section 3.12)."""

    def test_logout_token_is_accepted_only_by_logout_verifier(self):
        token = self.key.imzala(cikis_govdesi())
        self.assertIn(LOGOUT_EVENT, self.logout(token)["events"])
        self.assertEqual(self.error_code(self.identity, token, nonce=None), "malformed")
        self.assertEqual(self.error_code(self.identity, token, nonce="n-123"), "malformed")
        self.assertEqual(self.error_code(self.access, token), "malformed")

    def test_logout_token_with_matching_aud_and_azp_rejected_by_access_verifier(self):
        token = self.key.imzala(cikis_govdesi(aud="site-kiraci1", azp="identity-sync"))
        self.assertEqual(self.error_code(self.access, token), "malformed")

    def test_id_token_rejected_by_access_verifier(self):
        token = self.key.imzala(kimlik_govdesi(aud="site-kiraci1", azp="identity-sync"))
        self.assertEqual(self.error_code(self.access, token), "malformed")

    def test_access_token_rejected_by_id_verifier(self):
        token = self.key.imzala(erisim_govdesi(aud="press", azp="press", nonce="n-123"))
        self.assertEqual(self.error_code(self.identity, token), "malformed")
        self.assertEqual(self.error_code(self.identity, token, nonce=None), "malformed")

    def test_access_token_rejected_by_logout_verifier(self):
        # A well-formed access token (typ "Bearer") is not a logout token, so the code says so.
        token = self.key.imzala(erisim_govdesi(aud="press", jti="j-1", events={LOGOUT_EVENT: {}}, sid="s-1"))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")

    def test_events_claim_rejected_in_access_and_id_tokens(self):
        token = self.key.imzala(erisim_govdesi(events={LOGOUT_EVENT: {}}))
        self.assertEqual(self.error_code(self.access, token), "malformed")
        token = self.key.imzala(kimlik_govdesi(events={LOGOUT_EVENT: {}}))
        self.assertEqual(self.error_code(self.identity, token), "malformed")

    def test_tokens_without_typ_are_still_accepted(self):
        self.assertEqual(self.access(self.key.imzala(erisim_govdesi(typ=None)))["azp"], "identity-sync")
        self.assertEqual(self.identity(self.key.imzala(kimlik_govdesi(typ=None)))["sid"], "s-123")
        self.assertEqual(self.logout(self.key.imzala(cikis_govdesi(typ=None)))["sid"], "s-123")

    def test_non_string_typ_rejected(self):
        self.assertEqual(
            self.error_code(self.access, self.key.imzala(erisim_govdesi(typ=["Bearer"]))), "malformed"
        )
        self.assertEqual(self.error_code(self.identity, self.key.imzala(kimlik_govdesi(typ=1))), "malformed")
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(typ={}))), "malformed")

    def test_typ_check_is_case_sensitive(self):
        self.assertEqual(
            self.error_code(self.access, self.key.imzala(erisim_govdesi(typ="bearer"))), "malformed"
        )


class LogoutTokenClaimsTest(VerifierBase):
    """O2: required claims and claim shapes from OpenID Back-Channel Logout 1.0 section 2.4."""

    def test_missing_exp_is_malformed(self):
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(exp=None))), "malformed")

    def test_missing_jti_is_malformed(self):
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(jti=None))), "malformed")

    def test_missing_iat_is_malformed(self):
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(iat=None))), "malformed")

    def test_missing_iss_stays_wrong_issuer(self):
        self.assertEqual(
            self.error_code(self.logout, self.key.imzala(cikis_govdesi(iss=None))), "wrong_issuer"
        )

    def test_jti_must_be_non_empty_string(self):
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(jti=""))), "malformed")
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(jti=42))), "malformed")
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(jti=["j"]))), "malformed")

    def test_events_must_be_object(self):
        token = sign_raw(self.key, cikis_govdesi(events="x") | {"events": None})
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")
        token = self.key.imzala(cikis_govdesi(events="http://schemas.openid.net/event/backchannel-logout"))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")
        token = self.key.imzala(cikis_govdesi(events=[LOGOUT_EVENT]))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")

    def test_event_value_must_be_object(self):
        token = self.key.imzala(cikis_govdesi(events={LOGOUT_EVENT: "yes"}))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")
        token = sign_raw(self.key, cikis_govdesi(events={LOGOUT_EVENT: None}))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")
        token = self.key.imzala(cikis_govdesi(events={LOGOUT_EVENT: []}))
        self.assertEqual(self.error_code(self.logout, token), "not_logout_token")

    def test_sid_and_sub_must_be_non_empty_strings_when_present(self):
        self.assertEqual(
            self.error_code(self.logout, self.key.imzala(cikis_govdesi(sid=7))), "not_logout_token"
        )
        self.assertEqual(
            self.error_code(self.logout, self.key.imzala(cikis_govdesi(sid=""))), "not_logout_token"
        )
        # A non-string `sub` violates RFC 7519 itself; PyJWT rejects it before the logout checks run.
        self.assertEqual(self.error_code(self.logout, self.key.imzala(cikis_govdesi(sub=7))), "malformed")
        self.assertEqual(
            self.error_code(self.logout, self.key.imzala(cikis_govdesi(sid=None, sub=""))), "not_logout_token"
        )

    def test_expired_logout_token(self):
        now = int(time.time())
        token = self.key.imzala(cikis_govdesi(iat=now - 400, exp=now - 60))
        self.assertEqual(self.error_code(self.logout, token), "expired")

    def test_valid_logout_token_still_passes(self):
        claims = self.logout(self.key.imzala(cikis_govdesi()))
        self.assertEqual(claims["jti"], "j-123")


class StaleKeyWindowTest(unittest.TestCase):
    """O3: stale keys are served only for `ttl_seconds + max_stale_seconds` after the last good load."""

    def setUp(self):
        self.key = Anahtar("kid-1")
        self.fetcher = SahteJwks(self.key)
        self.now = [1000.0]
        self.cache = JwksCache(
            JWKS_URL,
            ttl_seconds=600,
            fetcher=self.fetcher,
            clock=lambda: self.now[0],
            min_refresh_seconds=5.0,
            max_stale_seconds=3600,
        )
        self.token = self.key.imzala(erisim_govdesi())

    def access(self, token=None, cache=None):
        return verify_access_token(
            token or self.token,
            cache=cache or self.cache,
            issuer=ISSUER,
            audience="site-kiraci1",
            allowed_azp={"identity-sync"},
            leeway=30,
        )

    def test_default_max_stale_seconds(self):
        self.assertEqual(JwksCache("https://kimlik.example/certs").max_stale_seconds, 3600)

    def test_stale_key_served_inside_window_and_refused_after(self):
        self.assertEqual(self.access()["azp"], "identity-sync")
        self.fetcher.hata = URLError("no connection")
        # Inside the window: ttl expired, refresh fails, the cached key is still served.
        self.now[0] += 600 + 3599
        self.assertEqual(self.access()["azp"], "identity-sync")
        self.assertEqual(self.fetcher.cagri, 2)
        # Past the window: the same kid raises JwksUnavailable even though it is in memory.
        self.now[0] += 10
        with self.assertRaises(JwksUnavailable):
            self.access()
        self.assertEqual(self.fetcher.cagri, 3)
        # Throttled retry inside min_refresh_seconds still refuses; no new fetch.
        self.now[0] += 1
        with self.assertRaises(JwksUnavailable):
            self.access()
        self.assertEqual(self.fetcher.cagri, 3)

    def test_successful_fetch_after_window_recovers(self):
        self.assertEqual(self.access()["azp"], "identity-sync")
        self.fetcher.hata = URLError("no connection")
        self.now[0] += 600 + 3600 + 1
        with self.assertRaises(JwksUnavailable):
            self.access()
        self.fetcher.hata = None
        self.now[0] += 6
        self.assertEqual(self.access()["azp"], "identity-sync")
        self.assertEqual(self.fetcher.cagri, 3)
        # The window restarts from the new load.
        self.fetcher.hata = URLError("no connection")
        self.now[0] += 600 + 3000
        self.assertEqual(self.access()["azp"], "identity-sync")

    def test_zero_max_stale_refuses_right_after_ttl(self):
        cache = JwksCache(
            JWKS_URL, ttl_seconds=600, fetcher=self.fetcher, clock=lambda: self.now[0], max_stale_seconds=0
        )
        self.assertEqual(self.access(cache=cache)["azp"], "identity-sync")
        self.fetcher.hata = URLError("no connection")
        self.now[0] += 601
        with self.assertRaises(JwksUnavailable):
            self.access(cache=cache)


class _OversizedJwksHandler(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        return


class JwksFetchBoundsTest(unittest.TestCase):
    """O4: readers do not wait for an in-flight fetch; one refresh at a time; bounded HTTP body."""

    def access(self, token, cache):
        return verify_access_token(
            token,
            cache=cache,
            issuer=ISSUER,
            audience="site-kiraci1",
            allowed_azp={"identity-sync"},
            leeway=30,
        )

    def test_cached_kid_does_not_wait_for_in_flight_refresh(self):
        key = Anahtar("kid-1")
        inner = SahteJwks(key)
        started = threading.Event()
        now = [1000.0]

        def slow_fetcher():
            data = inner()
            if inner.cagri > 1:
                started.set()
                time.sleep(1.0)
            return data

        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=slow_fetcher, clock=lambda: now[0])
        token = key.imzala(erisim_govdesi())
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
        now[0] += 601
        refresher = threading.Thread(target=self.access, args=(token, cache))
        refresher.start()
        try:
            self.assertTrue(started.wait(5.0))
            begin = time.monotonic()
            self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
            elapsed = time.monotonic() - begin
        finally:
            refresher.join(10.0)
        self.assertLess(elapsed, 0.5, f"cached-kid reader waited {elapsed:.3f}s for the network fetch")
        self.assertEqual(inner.cagri, 2)

    def test_concurrent_unknown_kid_calls_trigger_one_fetch(self):
        key = Anahtar("kid-1")
        new_key = Anahtar("kid-2")
        inner = SahteJwks(key)
        worker_count = 8
        in_fetch = threading.Semaphore(0)

        def slow_fetcher():
            data = inner()
            if inner.cagri > 1:
                in_fetch.release()
                time.sleep(0.3)
            return data

        cache = JwksCache(JWKS_URL, ttl_seconds=600, fetcher=slow_fetcher)
        self.assertEqual(self.access(key.imzala(erisim_govdesi()), cache)["azp"], "identity-sync")
        inner.anahtarlar.append(new_key)
        token = new_key.imzala(erisim_govdesi())
        gate = threading.Barrier(worker_count)
        results: list[object] = []
        lock = threading.Lock()

        def worker():
            gate.wait()
            try:
                result = self.access(token, cache)["azp"]
            except Exception as error:  # noqa: BLE001
                result = error
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(worker_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10.0)
        self.assertEqual(results, ["identity-sync"] * worker_count)
        self.assertEqual(inner.cagri, 2)

    def _serve(self, body: bytes) -> tuple[http.server.HTTPServer, str]:
        handler = type("Handler", (_OversizedJwksHandler,), {"body": body})
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, f"http://127.0.0.1:{server.server_address[1]}/certs"

    def test_oversized_jwks_body_is_rejected_on_cold_cache(self):
        key = Anahtar("kid-1")
        padding = b" " * (1_048_576 + 1)
        body = b'{"keys": [' + padding + json.dumps(key.jwk()).encode() + b"]}"
        _, url = self._serve(body)
        cache = JwksCache(url, ttl_seconds=600)
        with self.assertRaises(JwksUnavailable):
            self.access(key.imzala(erisim_govdesi()), cache)

    def test_oversized_body_keeps_warm_keys(self):
        key = Anahtar("kid-1")
        now = [1000.0]
        _, url = self._serve(b"[" + b"1," * 40 + b"1]")
        cache = JwksCache(url, ttl_seconds=600, fetcher=SahteJwks(key), clock=lambda: now[0])
        token = key.imzala(erisim_govdesi())
        self.assertEqual(self.access(token, cache)["azp"], "identity-sync")
        # Swap in the real HTTP fetcher with a tiny cap: the body is too large, warm keys stay.
        small = JwksCache(url, ttl_seconds=600, clock=lambda: now[0], max_bytes=16)
        small._keys, small._loaded_at = dict(cache._keys), cache._loaded_at
        now[0] += 601
        self.assertEqual(self.access(token, small)["azp"], "identity-sync")

    def test_http_fetcher_reads_body_within_cap(self):
        key = Anahtar("kid-1")
        _, url = self._serve(json.dumps({"keys": [key.jwk()]}).encode())
        cache = JwksCache(url, ttl_seconds=600)
        self.assertEqual(self.access(key.imzala(erisim_govdesi()), cache)["azp"], "identity-sync")

    def test_default_max_bytes(self):
        self.assertEqual(JwksCache("https://kimlik.example/certs").max_bytes, 1_048_576)


class MalformedTimeClaimsTest(VerifierBase):
    """K1: non-numeric, boolean or non-finite exp/iat/nbf must be `malformed`, never a leaked exception."""

    def test_malformed_time_claims_are_malformed_on_every_pyjwt(self):
        cases = {
            "exp=[]": {"exp": []},
            "exp={}": {"exp": {}},
            "exp=True": {"exp": True},
            "exp=False": {"exp": False},
            'exp="123"': {"exp": "123"},
            "exp=Infinity": {"exp": float("inf")},
            "exp=-Infinity": {"exp": float("-inf")},
            "exp=NaN": {"exp": float("nan")},
            "exp=null": {"exp": None},
            'iat="x"': {"iat": "x"},
            "iat=True": {"iat": True},
            "iat=Infinity": {"iat": float("inf")},
            "iat=[]": {"iat": []},
            "nbf=[]": {"nbf": []},
            "nbf=True": {"nbf": True},
            'nbf="x"': {"nbf": "x"},
            "nbf=Infinity": {"nbf": float("inf")},
            "nbf=null": {"nbf": None},
        }
        for name, change in cases.items():
            with self.subTest(claim=name):
                payload = erisim_govdesi()
                payload.update(change)
                try:
                    self.access(sign_raw(self.key, payload))
                except TokenError as error:
                    self.assertEqual(error.code, "malformed")
                else:
                    self.fail("token accepted")

    def test_malformed_time_claims_in_id_and_logout_tokens(self):
        payload = kimlik_govdesi()
        payload["exp"] = []
        self.assertEqual(self.error_code(self.identity, sign_raw(self.key, payload)), "malformed")
        payload = cikis_govdesi()
        payload["iat"] = float("inf")
        self.assertEqual(self.error_code(self.logout, sign_raw(self.key, payload)), "malformed")

    def test_float_time_claims_are_accepted(self):
        now = time.time()
        payload = erisim_govdesi(iat=now - 1.5, exp=now + 300.5, nbf=now - 1.5)
        self.assertEqual(self.access(sign_raw(self.key, payload))["azp"], "identity-sync")

    def test_error_message_does_not_leak_claim_values(self):
        payload = erisim_govdesi()
        payload["exp"] = "secret-marker-value"
        with self.assertRaises(TokenError) as caught:
            self.access(sign_raw(self.key, payload))
        self.assertNotIn("secret-marker", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
