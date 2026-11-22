"""Test key and token generation. Keys are generated locally for each run."""

from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "http://identity.localhost:5070/realms/platform"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


class Anahtar:
    def __init__(self, kid: str):
        self.kid = kid
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = self.private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def jwk(self) -> dict:
        jwks_payload = RSAAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        jwks_payload.update({"kid": self.kid, "alg": "RS256", "use": "sig"})
        return jwks_payload

    def sign(self, payload: dict, alg: str = "RS256", kid: str | None = None) -> str:
        headers = {"kid": kid or self.kid}
        if alg == "none":
            return jwt.encode(payload, key=None, algorithm="none", headers=headers)
        return jwt.encode(payload, self.private_pem, algorithm=alg, headers=headers)


def jwks(*keys: Anahtar) -> dict:
    return {"keys": [a.jwk() for a in keys]}


def access_payload(**overrides) -> dict:
    simdi = int(time.time())
    payload = {
        "iss": ISSUER,
        "sub": "service-account-identity-sync",
        "aud": "site-tenant1",
        "azp": "identity-sync",
        "iat": simdi,
        "exp": simdi + 300,
        "typ": "Bearer",
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


def identity_payload(**overrides) -> dict:
    simdi = int(time.time())
    payload = {
        "iss": ISSUER,
        "sub": "f0d6f4d2-0000-4000-8000-000000000001",
        "aud": "press",
        "azp": "press",
        "iat": simdi,
        "exp": simdi + 300,
        "auth_time": simdi,
        "nonce": "n-123",
        "sid": "s-123",
        "typ": "ID",
        "email": "ayse.ornek@example.test",
        "email_verified": True,
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


def logout_payload(**overrides) -> dict:
    simdi = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": "press",
        "iat": simdi,
        "exp": simdi + 120,
        "jti": "j-123",
        "sub": "f0d6f4d2-0000-4000-8000-000000000001",
        "sid": "s-123",
        "events": {LOGOUT_EVENT: {}},
        "typ": "Logout",
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


class FakeJwks:
    """Fake fetcher for JwksCache. Tracks call count without using the network.

    Each call raises `error` when set. `ham` adds extra raw JWK entries to the key set.
    """

    def __init__(self, *keys: Anahtar):
        self.keys = list(keys)
        self.ham: list[dict] = []
        self.error: Exception | None = None
        self.call_count = 0

    def __call__(self) -> dict:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        jwks_payload = jwks(*self.keys)
        jwks_payload["keys"] = list(self.ham) + jwks_payload["keys"]
        return jwks_payload
