"""Belirteç doğrulama işlevleri."""

from __future__ import annotations

import time
from collections.abc import Iterable

import jwt

from oidc_verify.hatalar import TokenError
from oidc_verify.jwks import JwksCache

ALGORITMA = "RS256"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


def _baslik(token: str) -> dict:
    if not isinstance(token, str) or token.count(".") != 2:
        raise TokenError("malformed")
    try:
        return jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as hata:
        raise TokenError("malformed") from hata


def _coz(token: str, *, cache: JwksCache, issuer: str, leeway: int, require: Iterable[str]) -> dict:
    """İmzayı, iss ve süreyi denetler. aud ve azp denetimini çağırana bırakır."""
    baslik = _baslik(token)
    if baslik.get("alg") != ALGORITMA:
        raise TokenError("invalid_signature")
    kid = baslik.get("kid")
    if not kid or not isinstance(kid, str):
        raise TokenError("malformed")
    anahtar = cache.get_signing_key(kid)
    try:
        return jwt.decode(
            token,
            anahtar,
            algorithms=[ALGORITMA],
            issuer=issuer,
            leeway=leeway,
            options={"require": list(require), "verify_aud": False},
        )
    except jwt.exceptions.InvalidSignatureError as hata:
        raise TokenError("invalid_signature") from hata
    except jwt.exceptions.ExpiredSignatureError as hata:
        raise TokenError("expired") from hata
    except jwt.exceptions.ImmatureSignatureError as hata:
        raise TokenError("not_yet_valid") from hata
    except jwt.exceptions.InvalidIssuerError as hata:
        raise TokenError("wrong_issuer") from hata
    except jwt.exceptions.MissingRequiredClaimError as hata:
        if hata.claim == "iss":
            raise TokenError("wrong_issuer") from hata
        raise TokenError("malformed") from hata
    except jwt.exceptions.InvalidAlgorithmError as hata:
        raise TokenError("invalid_signature") from hata
    except jwt.exceptions.DecodeError as hata:
        raise TokenError("malformed") from hata
    except jwt.exceptions.InvalidTokenError as hata:
        raise TokenError("malformed") from hata


def _tek_aud(claims: dict, beklenen: str) -> None:
    aud = claims.get("aud")
    if isinstance(aud, list):
        if len(aud) != 1:
            raise TokenError("wrong_audience")
        aud = aud[0]
    if not isinstance(aud, str) or aud != beklenen:
        raise TokenError("wrong_audience")


def _iat_denetle(claims: dict, leeway: int) -> None:
    iat = claims.get("iat")
    if not isinstance(iat, int | float) or isinstance(iat, bool):
        raise TokenError("malformed")
    if iat > time.time() + leeway:
        raise TokenError("not_yet_valid")


def verify_access_token(
    token: str,
    *,
    cache: JwksCache,
    issuer: str,
    audience: str,
    allowed_azp: Iterable[str],
    leeway: int = 30,
) -> dict:
    """Servis belirtecini doğrular. `aud` tek değer ve `audience` olmalı. `azp` izin listesinde olmalı."""
    claims = _coz(token, cache=cache, issuer=issuer, leeway=leeway, require=["exp", "iss"])
    _tek_aud(claims, audience)
    azp = claims.get("azp")
    if not isinstance(azp, str) or azp not in set(allowed_azp):
        raise TokenError("wrong_azp")
    return claims


def verify_id_token(
    token: str,
    *,
    cache: JwksCache,
    issuer: str,
    client_id: str,
    nonce: str | None,
    leeway: int = 30,
) -> dict:
    """Kimlik belirtecini doğrular. `aud` tek değer ve `client_id` olmalı. `nonce` eşleşmeli."""
    claims = _coz(token, cache=cache, issuer=issuer, leeway=leeway, require=["exp", "iss", "sub", "iat"])
    _tek_aud(claims, client_id)
    azp = claims.get("azp")
    if azp is not None and azp != client_id:
        raise TokenError("wrong_azp")
    if nonce is not None and claims.get("nonce") != nonce:
        raise TokenError("wrong_nonce")
    return claims


def verify_logout_token(
    token: str,
    *,
    cache: JwksCache,
    issuer: str,
    client_id: str,
    leeway: int = 30,
) -> dict:
    """Keycloak çıkış belirtecini doğrular (OpenID Connect Back-Channel Logout 1.0)."""
    claims = _coz(token, cache=cache, issuer=issuer, leeway=leeway, require=["iss"])
    _tek_aud(claims, client_id)
    _iat_denetle(claims, leeway)
    events = claims.get("events")
    if not isinstance(events, dict) or LOGOUT_EVENT not in events:
        raise TokenError("not_logout_token")
    if not claims.get("sid") and not claims.get("sub"):
        raise TokenError("not_logout_token")
    if "nonce" in claims:
        raise TokenError("not_logout_token")
    return claims
