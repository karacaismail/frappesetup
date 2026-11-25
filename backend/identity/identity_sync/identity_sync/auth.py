"""Build the service token verifier.

The shared `oidc_verify` library verifies tokens (`docs/sozlesmeler.md`, section 3).
The service has no separate verification implementation. Without the library, every request is rejected.

There are five client lists (O-38):

- `execute_azp` and `session_azp` contain the same configured tenant service clients.
  They execute approved invitations and resolve operations only in their own organization.
  They may also revoke sessions of their own members.
- `operator_azp` alone grants access to platform reconciliation, replay and queue lists.
- `preview_azp` permits invitation previews, never platform queue access or execution.
- `deletion_azp` permits Press to request global account deletion and the removal of old keys after an approved recovery.

Operator, preview and deletion lists are disjoint from each other and from tenant lists.
They must not contain any client whose name starts with `site-`.

The server enforces the split. The verifier accepts the union of the four lists.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from identity_sync.config import Settings

Verifier = Callable[[str], Mapping[str, object]]

LEEWAY_SECONDS = 30
JWKS_TTL_SECONDS = 600


class TokenRejected(Exception):
    """The token is invalid or could not be verified."""


def reject_all(_token: str) -> Mapping[str, object]:
    raise TokenRejected("verifier_unavailable")


def build_verifier(settings: Settings) -> Verifier:
    """Return the `oidc_verify` verifier, or `reject_all` if the library is unavailable."""
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
