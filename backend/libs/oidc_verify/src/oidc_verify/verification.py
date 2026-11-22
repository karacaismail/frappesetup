"""Token verification functions."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable

import jwt

from oidc_verify.errors import TokenError
from oidc_verify.jwks import JwksCache

ALGORITHM = "RS256"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"

# Payload `typ` values Keycloak 26 sets. A token without `typ` is accepted; a wrong one is rejected.
TYP_ACCESS = "Bearer"
TYP_ID = "ID"
TYP_LOGOUT = "Logout"

TIME_CLAIMS = ("exp", "iat", "nbf")

# PyJWT 2.13 lets TypeError/OverflowError escape from jwt.decode for list/dict/inf time claims.
_DECODE_LEAKS = (TypeError, ValueError, OverflowError)


def _header(token: str) -> dict:
    if not isinstance(token, str) or token.count(".") != 2:
        raise TokenError("malformed")
    try:
        return jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as error:
        raise TokenError("malformed") from error


def _check_time_claims(claims: dict) -> None:
    """exp, iat and nbf must be finite numbers when present. bool is excluded (it is an int subclass)."""
    for name in TIME_CLAIMS:
        if name not in claims:
            continue
        value = claims[name]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TokenError("malformed")
        if isinstance(value, float) and not math.isfinite(value):
            raise TokenError("malformed")


def _unverified_claims(token: str) -> dict:
    """Parses the payload without verifying anything. Used only to reject malformed time claims early."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except _DECODE_LEAKS as error:
        raise TokenError("malformed") from error
    except jwt.exceptions.PyJWTError as error:
        raise TokenError("malformed") from error
    if not isinstance(claims, dict):
        raise TokenError("malformed")
    return claims


def _coz(token: str, *, cache: JwksCache, issuer: str, leeway: int, require: Iterable[str]) -> dict:
    """Verify the signature, issuer and time claims. The caller checks `aud` and `azp`."""
    header = _header(token)
    if header.get("alg") != ALGORITHM:
        raise TokenError("invalid_signature")
    kid = header.get("kid")
    if not kid or not isinstance(kid, str):
        raise TokenError("malformed")
    # Type-check the time claims before PyJWT compares them, so bool/str values are reported as
    # malformed instead of expired and PyJWT 2.13 never sees a value it cannot convert.
    _check_time_claims(_unverified_claims(token))
    anahtar = cache.get_signing_key(kid)
    try:
        claims = jwt.decode(
            token,
            anahtar,
            algorithms=[ALGORITHM],
            issuer=issuer,
            leeway=leeway,
            options={"require": list(require), "verify_aud": False},
        )
    except jwt.exceptions.InvalidSignatureError as error:
        raise TokenError("invalid_signature") from error
    except jwt.exceptions.ExpiredSignatureError as error:
        raise TokenError("expired") from error
    except jwt.exceptions.ImmatureSignatureError as error:
        raise TokenError("not_yet_valid") from error
    except jwt.exceptions.InvalidIssuerError as error:
        raise TokenError("wrong_issuer") from error
    except jwt.exceptions.MissingRequiredClaimError as error:
        if error.claim == "iss":
            raise TokenError("wrong_issuer") from error
        raise TokenError("malformed") from error
    except jwt.exceptions.InvalidAlgorithmError as error:
        raise TokenError("invalid_signature") from error
    except jwt.exceptions.DecodeError as error:
        raise TokenError("malformed") from error
    except jwt.exceptions.InvalidTokenError as error:
        raise TokenError("malformed") from error
    except _DECODE_LEAKS as error:
        raise TokenError("malformed") from error
    if not isinstance(claims, dict):
        raise TokenError("malformed")
    _check_time_claims(claims)
    return claims


def _check_token_type(
    claims: dict, expected_typ: str, *, allow_events: bool, wrong_type_code: str = "malformed"
) -> None:
    """Explicit typing (RFC 8725 section 3.12).

    A non-string `typ` is malformed. A string `typ` of another type is reported with `wrong_type_code`.
    An unexpected `events` claim is malformed.
    """
    typ = claims.get("typ")
    if "typ" in claims:
        if not isinstance(typ, str):
            raise TokenError("malformed")
        if typ != expected_typ:
            raise TokenError(wrong_type_code)
    if not allow_events and "events" in claims:
        raise TokenError("malformed")


def _single_aud(claims: dict, beklenen: str) -> None:
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


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def verify_access_token(
    token: str,
    *,
    cache: JwksCache,
    issuer: str,
    audience: str,
    allowed_azp: Iterable[str],
    leeway: int = 30,
) -> dict:
    """Verify a service token. Only `audience` is allowed in `aud`. `azp` must be on the allowlist."""
    claims = _coz(token, cache=cache, issuer=issuer, leeway=leeway, require=["exp", "iss"])
    _check_token_type(claims, TYP_ACCESS, allow_events=False)
    _single_aud(claims, audience)
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
    """Verify an ID token. Only `client_id` is allowed in `aud`. The expected `nonce` must match."""
    claims = _coz(token, cache=cache, issuer=issuer, leeway=leeway, require=["exp", "iss", "sub", "iat"])
    _check_token_type(claims, TYP_ID, allow_events=False)
    _single_aud(claims, client_id)
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
    """Verify a Keycloak logout token (OpenID Connect Back-Channel Logout 1.0 section 2.4)."""
    claims = _coz(token, cache=cache, issuer=issuer, leeway=leeway, require=["iss", "exp", "iat", "jti"])
    # A well-formed token of another type is "not a logout token" rather than malformed.
    _check_token_type(claims, TYP_LOGOUT, allow_events=True, wrong_type_code="not_logout_token")
    _single_aud(claims, client_id)
    _iat_denetle(claims, leeway)
    if not _non_empty_str(claims.get("jti")):
        raise TokenError("malformed")
    events = claims.get("events")
    if not isinstance(events, dict) or not isinstance(events.get(LOGOUT_EVENT), dict):
        raise TokenError("not_logout_token")
    if "sid" in claims and not _non_empty_str(claims["sid"]):
        raise TokenError("not_logout_token")
    if "sub" in claims and not _non_empty_str(claims["sub"]):
        raise TokenError("not_logout_token")
    if "sid" not in claims and "sub" not in claims:
        raise TokenError("not_logout_token")
    if "nonce" in claims:
        raise TokenError("not_logout_token")
    return claims
