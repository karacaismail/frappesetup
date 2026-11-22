"""Test anahtarları ve belirteç üretimi. Anahtarlar her çalıştırmada yerelde üretilir."""

from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "http://kimlik.localhost:5070/realms/platform"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


class Anahtar:
    def __init__(self, kid: str):
        self.kid = kid
        self.ozel = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.ozel_pem = self.ozel.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def jwk(self) -> dict:
        veri = RSAAlgorithm.to_jwk(self.ozel.public_key(), as_dict=True)
        veri.update({"kid": self.kid, "alg": "RS256", "use": "sig"})
        return veri

    def imzala(self, govde: dict, alg: str = "RS256", kid: str | None = None) -> str:
        basliklar = {"kid": kid or self.kid}
        if alg == "none":
            return jwt.encode(govde, key=None, algorithm="none", headers=basliklar)
        return jwt.encode(govde, self.ozel_pem, algorithm=alg, headers=basliklar)


def jwks(*anahtarlar: Anahtar) -> dict:
    return {"keys": [a.jwk() for a in anahtarlar]}


def erisim_govdesi(**degisiklik) -> dict:
    simdi = int(time.time())
    govde = {
        "iss": ISSUER,
        "sub": "service-account-identity-sync",
        "aud": "site-kiraci1",
        "azp": "identity-sync",
        "iat": simdi,
        "exp": simdi + 300,
        "typ": "Bearer",
    }
    govde.update(degisiklik)
    return {k: v for k, v in govde.items() if v is not None}


def kimlik_govdesi(**degisiklik) -> dict:
    simdi = int(time.time())
    govde = {
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
    govde.update(degisiklik)
    return {k: v for k, v in govde.items() if v is not None}


def cikis_govdesi(**degisiklik) -> dict:
    simdi = int(time.time())
    govde = {
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
    govde.update(degisiklik)
    return {k: v for k, v in govde.items() if v is not None}


class SahteJwks:
    """JwksCache için ağ yerine geçen sağlayıcı. Çağrı sayısını sayar."""

    def __init__(self, *anahtarlar: Anahtar):
        self.anahtarlar = list(anahtarlar)
        self.cagri = 0

    def __call__(self) -> dict:
        self.cagri += 1
        return jwks(*self.anahtarlar)
