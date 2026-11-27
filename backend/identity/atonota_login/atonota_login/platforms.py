# SPDX-License-Identifier: MIT
"""`atonota_login` sign-in platforms (G-159).

Each JSON file in ``platforms/`` describes one sign-in platform. In Keycloak a platform is an
identity provider. The list of platforms is data: this module holds no platform names, so a new
platform is opened by adding one file.

Secrets never enter the data. A record names the environment variables that hold them. A platform
opens only when every named variable has a value; otherwise it stays closed and hidden on the
login page. The safety fields (e-mail trust, linking flows) are fixed here, not in the data.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PRODUCT_DIR = Path(__file__).resolve().parents[1]
REGISTRY_DIR = PRODUCT_DIR / "platforms"
REALM = "platform"
FIRST_BROKER_FLOW = "atonota-first-broker-login"
POST_BROKER_FLOW = "atonota-post-broker"
LOGIN_HOST_PREFIX = "api.login."

ALIAS = re.compile(r"[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?")
PROVIDER_ID = re.compile(r"[a-z][a-z0-9-]{0,62}")
ENV_NAME = re.compile(r"ATONOTA_[A-Z0-9_]+")
HOST = re.compile(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
LOCAL_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.localhost)")
SECRET_LIKE_KEY = re.compile(r"secret|password|private", re.IGNORECASE)
RECORD_KEYS = {"alias", "providerId", "displayName", "authorizationHost", "secrets", "config", "active"}
REQUIRED_KEYS = {"alias", "providerId", "displayName", "authorizationHost", "secrets", "config"}
# Keycloak's "essential claim" check. An open platform must prove the e-mail is verified, or a person
# could claim someone else's address before that person registers (account pre-hijack).
VERIFIED_EMAIL_CLAIM = {"filteredByClaim": "true", "claimFilterName": "email_verified", "claimFilterValue": "true"}
# Config values that turn off a safety check. The data may not set them (review 1, minor 4).
WEAKENING_VALUES = {
    "validateSignature": {"false"},
    "clientAuthMethod": {"none"},
    "pkceEnabled": {"false"},
}
# Fields the data may not set. They keep linking safe (G-160) and the platform closed until opened.
FIXED_FIELDS = {
    "trustEmail": False,
    "storeToken": False,
    "addReadTokenRoleOnCreate": False,
    "linkOnly": False,
    "firstBrokerLoginFlowAlias": FIRST_BROKER_FLOW,
    "postBrokerLoginFlowAlias": POST_BROKER_FLOW,
}


class RegistryError(ValueError):
    """The registry or a setting breaks a rule. The message never holds a secret value."""


@dataclass(frozen=True)
class Platform:
    alias: str
    provider_id: str
    display_name: str
    authorization_host: str
    secrets: Mapping[str, str]
    config: Mapping[str, str]
    active: bool = True
    source: Path = field(default=Path(), compare=False)


def _check_record(record: object, path: Path, allow_local_http: bool) -> Platform:
    where = path.name
    if not isinstance(record, dict):
        raise RegistryError(f"{where}: the record must be a JSON object.")
    unknown = set(record) - RECORD_KEYS
    if unknown:
        raise RegistryError(f"{where}: unknown or fixed keys: {', '.join(sorted(unknown))}.")
    missing = REQUIRED_KEYS - set(record)
    if missing:
        raise RegistryError(f"{where}: missing keys: {', '.join(sorted(missing))}.")
    alias = record["alias"]
    if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
        raise RegistryError(f"{where}: the alias must be lowercase letters, digits and dashes.")
    if path.stem != alias:
        raise RegistryError(f"{where}: the file name must be {alias}.json.")
    if not isinstance(record["providerId"], str) or not PROVIDER_ID.fullmatch(record["providerId"]):
        raise RegistryError(f"{where}: providerId is not a Keycloak provider id.")
    if not isinstance(record["displayName"], str) or not record["displayName"].strip():
        raise RegistryError(f"{where}: displayName is empty.")
    host = record["authorizationHost"]
    if not isinstance(host, str) or not HOST.fullmatch(host):
        raise RegistryError(f"{where}: authorizationHost must be a bare host name.")
    secrets = record["secrets"]
    if not isinstance(secrets, dict) or "clientId" not in secrets:
        raise RegistryError(f"{where}: secrets must name at least the clientId variable.")
    for key, name in secrets.items():
        if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
            raise RegistryError(f"{where}: the variable for {key} must look like ATONOTA_NAME.")
    config = record["config"]
    if not isinstance(config, dict):
        raise RegistryError(f"{where}: config must be an object.")
    for key, value in config.items():
        if key in secrets or SECRET_LIKE_KEY.search(key):
            raise RegistryError(f"{where}: config key {key} looks secret. Name it under secrets.")
        if not isinstance(value, str) or "${" in value:
            raise RegistryError(f"{where}: config value of {key} must be plain text.")
        if value.strip().lower() in WEAKENING_VALUES.get(key, set()):
            raise RegistryError(f"{where}: config {key}={value} turns off a safety check.")
        if "://" in value:
            address = urllib.parse.urlsplit(value)
            local = allow_local_http and address.scheme == "http" and LOCAL_HOST.fullmatch(address.hostname or "")
            if address.scheme != "https" and not local:
                raise RegistryError(f"{where}: config {key} must use https.")
    active = record.get("active", True)
    if not isinstance(active, bool):
        raise RegistryError(f"{where}: active must be true or false.")
    if active and any(config.get(key) != value for key, value in VERIFIED_EMAIL_CLAIM.items()):
        raise RegistryError(
            f"{where}: an active platform must require email_verified=true "
            "(filteredByClaim, claimFilterName, claimFilterValue). Otherwise set active to false."
        )
    return Platform(alias, record["providerId"], record["displayName"], host, dict(secrets), dict(config), active, path)


def load_platforms(directory: Path = REGISTRY_DIR, *, allow_local_http: bool = False) -> list[Platform]:
    """Read and check every platform record, sorted by alias.

    Addresses must use https. ``allow_local_http`` also accepts http to a local name. Only the
    development apply step may set it: in production Keycloak would look for that name on its own
    machine (review 2, finding 2).
    """
    found = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise RegistryError(f"{path.name}: not valid JSON ({error.__class__.__name__}).") from None
        found.append(_check_record(record, path, allow_local_http))
    names = [name for platform in found for name in platform.secrets.values()]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise RegistryError(f"Two platforms share a variable: {', '.join(duplicates)}.")
    return sorted(found, key=lambda platform: platform.alias)


def _entry(platform: Platform, enabled: bool, secret_config: Mapping[str, str]) -> dict:
    return {
        "alias": platform.alias,
        "displayName": platform.display_name,
        "providerId": platform.provider_id,
        "enabled": enabled,
        "trustEmail": FIXED_FIELDS["trustEmail"],
        "storeToken": FIXED_FIELDS["storeToken"],
        "addReadTokenRoleOnCreate": FIXED_FIELDS["addReadTokenRoleOnCreate"],
        "linkOnly": FIXED_FIELDS["linkOnly"],
        "hideOnLogin": not enabled,
        "firstBrokerLoginFlowAlias": FIXED_FIELDS["firstBrokerLoginFlowAlias"],
        "config": {**secret_config, **platform.config},
        "postBrokerLoginFlowAlias": FIXED_FIELDS["postBrokerLoginFlowAlias"],
    }


def realm_entry(platform: Platform) -> dict:
    """The realm file entry: closed, hidden, secrets as Keycloak import placeholders."""
    placeholders = {key: "${" + name + "}" for key, name in platform.secrets.items()}
    return _entry(platform, False, placeholders)


def render_identity_providers(registry: list[Platform]) -> list[dict]:
    return [realm_entry(platform) for platform in registry]


def secret_values(platform: Platform, environment: Mapping[str, str]) -> dict | None:
    """The secret config of a platform, or None when any value is missing or blank."""
    values = {}
    for key, name in platform.secrets.items():
        value = environment.get(name, "")
        if not value.strip():
            return None
        values[key] = value
    return values


def desired_state(platform: Platform, environment: Mapping[str, str]) -> dict:
    """The Keycloak representation for this environment. Secrets come only from the environment."""
    values = secret_values(platform, environment) if platform.active else None
    if values is None:
        return _entry(platform, False, {key: "" for key in platform.secrets})
    return _entry(platform, True, values)


def _array_span(text: str, key: str) -> tuple[int, int, str]:
    """Start and end of a top-level array value in the realm file, and its line indent."""
    match = re.search(r'(?m)^(?P<indent>[ ]*)"' + re.escape(key) + r'": \[', text)
    if not match:
        raise RegistryError(f"The realm file has no {key} array.")
    start = match.end() - 1
    depth, index, in_string = 0, start, False
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return start, index + 1, match.group("indent")
        index += 1
    raise RegistryError(f"The {key} array is not closed.")


def replace_identity_providers(realm_text: str, registry: list[Platform]) -> str:
    """Return the realm file text with only the identityProviders array rewritten."""
    start, end, indent = _array_span(realm_text, "identityProviders")
    rendered = json.dumps(render_identity_providers(registry), indent=2, ensure_ascii=False)
    rendered = rendered.replace("\n", "\n" + indent)
    return realm_text[:start] + rendered + realm_text[end:]


def broker_redirect_uri(base_url: str, alias: str, *, allow_local_http: bool = False, realm: str = REALM) -> str:
    """The address a platform sends the browser back to, for its console's allowed list."""
    if not ALIAS.fullmatch(alias):
        raise RegistryError("The alias is not valid.")
    parts = urllib.parse.urlsplit(base_url)
    host = parts.hostname or ""
    local = allow_local_http and parts.scheme == "http" and LOCAL_HOST.fullmatch(host)
    if parts.scheme != "https" and not local:
        raise RegistryError("The login address must use https.")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise RegistryError("The login address must be scheme and host only.")
    if not local and (parts.port or not HOST.fullmatch(host)):
        raise RegistryError("The login address must be a bare host name.")
    origin = f"{parts.scheme}://{parts.netloc}"
    return f"{origin}/realms/{realm}/broker/{alias}/endpoint"


def read_env_file(path: Path) -> dict:
    """Read KEY=value lines. Blank lines and lines starting with # are skipped."""
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def login_host(environment: Mapping[str, str]) -> str:
    """The login host of an environment, checked against the api.login.<base> rule (ortamlar.md)."""
    base = environment.get("ATONOTA_BASE_HOST", "")
    host = environment.get("ATONOTA_ID_HOST", "")
    if not HOST.fullmatch(base):
        raise RegistryError("ATONOTA_BASE_HOST is not a host name.")
    if host != LOGIN_HOST_PREFIX + base:
        raise RegistryError("ATONOTA_ID_HOST must be api.login.<ATONOTA_BASE_HOST>.")
    return host


def environment_redirects(environment: Mapping[str, str], registry: list[Platform] | None = None) -> dict:
    host = login_host(environment)
    return {p.alias: broker_redirect_uri(f"https://{host}", p.alias) for p in registry or load_platforms()}
