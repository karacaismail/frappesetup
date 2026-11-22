"""Servis belirtecini doğrulayan işlevi kurar.

Doğrulamayı ortak `oidc_verify` kitaplığı yapar (`docs/sozlesmeler.md`, 3. bölüm).
Servis kendi doğrulama kodunu yazmaz. Kitaplık yoksa bütün istekler reddedilir.

There are four client lists. Each one grants a different right:

- `preview_azp` may read and preview.
- `execute_azp` may also execute. It holds the service clients of the tenant sites: the human
  approves in the AI layer of the tenant site, so that site starts the execution.
- `session_azp` may call `/v1/sessions/revoke`. It holds the same tenant site clients.
  A new tenant's client must be added to both lists, or it cannot execute or end a session.
- `deletion_azp` may only call `/v1/account-deletions`. It holds the Press service client.

The execute list and the session list may carry the same client. A client in the preview
list or in the deletion list cannot be in any other list (`config.load_settings` refuses it).

The server enforces the split. The verifier accepts the union of the four lists.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from identity_sync.config import Settings

Verifier = Callable[[str], Mapping[str, object]]

LEEWAY_SECONDS = 30
JWKS_TTL_SECONDS = 600


class TokenRejected(Exception):
    """Belirteç geçersiz ya da doğrulanamadı."""


def reject_all(_token: str) -> Mapping[str, object]:
    raise TokenRejected("verifier_unavailable")


def build_verifier(settings: Settings) -> Verifier:
    """`oidc_verify` ile çalışan doğrulayıcıyı döner. Kitaplık yoksa `reject_all` döner."""
    try:
        import oidc_verify
    except ImportError:
        return reject_all
    if not settings.known_azp:
        return reject_all
    cache = oidc_verify.JwksCache(settings.jwks_url, ttl_seconds=JWKS_TTL_SECONDS)

    def verify(token: str) -> Mapping[str, object]:
        try:
            return oidc_verify.verify_access_token(
                token,
                cache=cache,
                issuer=settings.issuer,
                audience=settings.service_audience,
                allowed_azp=set(settings.known_azp),
                leeway=LEEWAY_SECONDS,
            )
        except oidc_verify.TokenError as error:
            raise TokenRejected(getattr(error, "code", "invalid")) from None

    return verify
