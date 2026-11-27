"""`atonota_login` reads: the sign-in platforms of a tenant and the linked accounts of a member (AJA-459).

The replies are built from an allow list. Nothing of a Keycloak row passes through as it is:
no `config`, no secret, no outside user name, no credential data and no Keycloak id.

The panel contract is in `atonota-web`, `src/auth/README.md` (G-159 and G-160).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

# The panel accepts only this alias form. A row outside it would make the panel drop the whole list.
ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_DISPLAY_NAME = 80
MAX_PROVIDERS = 100
# Ways to sign in without a platform. A second factor such as `otp` is not one on its own.
LOCAL_SIGN_IN_TYPES = frozenset({"password", "webauthn-passwordless"})
# An unresolved setting placeholder, such as `${ATONOTA_GOOGLE_CLIENT_SECRET}`, is no secret.
# A vault reference, such as `${vault.google}`, is a stored secret.
_PLACEHOLDER = re.compile(r"^\$\{(?!vault\.).*\}$")


@dataclass(frozen=True)
class Platform:
    """One usable sign-in platform. `organization` is the Organization alias, empty for a general platform."""

    alias: str
    display_name: str
    organization: str = ""


def _has_secret(config: object) -> bool:
    if not isinstance(config, Mapping):
        return False
    secret = config.get("clientSecret")
    return isinstance(secret, str) and bool(secret.strip()) and not _PLACEHOLDER.fullmatch(secret.strip())


def _hidden(row: Mapping[str, object]) -> bool:
    # Keycloak 26 keeps the flag on the row. Older exports keep it in `config` as text.
    config = row.get("config")
    in_config = isinstance(config, Mapping) and str(config.get("hideOnLogin", "")).lower() == "true"
    return row.get("hideOnLogin") is True or in_config


def catalog(
    rows: Iterable[Mapping[str, object]], organization_alias_of: Callable[[str], str | None]
) -> tuple[Platform, ...]:
    """The usable platforms of the realm: enabled, with a secret, not link-only, with a valid alias.

    A general platform that is hidden on the login page is left out. A platform bound to an
    organization stays in: `visible_to` decides whether its tenant may see it. A platform bound
    to an organization that cannot be found is left out.
    """
    platforms: list[Platform] = []
    for row in rows:
        alias = row.get("alias")
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
            continue
        if row.get("enabled") is not True or row.get("linkOnly") is True or not _has_secret(row.get("config")):
            continue
        organization_id = row.get("organizationId")
        organization = ""
        if isinstance(organization_id, str) and organization_id:
            organization = organization_alias_of(organization_id) or ""
            if not organization:
                continue
        elif _hidden(row):
            continue
        name = row.get("displayName")
        display_name = name.strip() if isinstance(name, str) and name.strip() else alias
        platforms.append(Platform(alias, display_name[:MAX_DISPLAY_NAME], organization))
    return tuple(platforms)


def visible_to(platforms: Iterable[Platform], organization: str) -> tuple[Platform, ...]:
    """General platforms and the platforms of the tenant's own organization. Nothing of another tenant."""
    seen: set[str] = set()
    visible: list[Platform] = []
    for platform in platforms:
        if platform.organization and platform.organization != organization:
            continue
        if platform.alias in seen:
            continue
        seen.add(platform.alias)
        visible.append(platform)
    return tuple(visible[:MAX_PROVIDERS])


def provider_list(platforms: Iterable[Platform]) -> dict[str, object]:
    return {"providers": [{"alias": item.alias, "display_name": item.display_name} for item in platforms]}


def linked_accounts(
    platforms: Iterable[Platform],
    federated: Iterable[Mapping[str, object]],
    credentials: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """The tenant's platforms with a `linked` flag, and the number of local sign-in ways.

    A link to a platform outside the tenant's list is left out. Only the count of local
    credentials leaves the service. The panel needs nothing more.
    """
    linked = {str(row.get("identityProvider", "")) for row in federated}
    local = sum(1 for row in credentials if row.get("type") in LOCAL_SIGN_IN_TYPES)
    return {
        "providers": [
            {"alias": item.alias, "display_name": item.display_name, "linked": item.alias in linked}
            for item in platforms
        ],
        "local_sign_in_methods": local,
    }


class CatalogCache:
    """Keeps the realm's platform list for a short time. The linked accounts are never kept.

    The list holds no personal data. `clock` returns seconds and only moves forward.
    """

    def __init__(self, load: Callable[[], tuple[Platform, ...]], *, seconds: float, clock: Callable[[], float]) -> None:
        self._load = load
        self._seconds = seconds
        self._clock = clock
        self._value: tuple[Platform, ...] | None = None
        self._expires_at = 0.0

    def get(self) -> tuple[Platform, ...]:
        now = self._clock()
        if self._value is None or now >= self._expires_at:
            self._value = self._load()
            self._expires_at = now + self._seconds
        return self._value
