# SPDX-License-Identifier: MIT
"""Apply the platform registry to a running Keycloak through its Admin API (G-159).

Keycloak's realm import cannot open a platform only when its secret exists. This command does
that step and can run again:

- A platform whose secrets are all set opens and shows on the login page.
- A platform with a missing secret, or with ``"active": false``, is closed and hidden. Its stored
  secrets are cleared.
- Identity providers that are not in the registry stay as they are. Corporate providers of an
  organization are such providers. The command does not change them, but it checks them (G-160):
  ``trustEmail`` must be off, the broker flows must be the fixed ones, and the provider must require
  the ``email_verified`` claim. A provider without the claim needs a valid exception record from
  the exceptions file. Otherwise the command stops with an error. It does not close the provider.
- Nothing is deleted. No secret is printed.

By default only a local development Keycloak is accepted. A remote Keycloak needs https and an
explicit expected host, so the command cannot reach a wrong environment by mistake.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Mapping, Sequence

from atonota_login import platforms
from atonota_login.platforms import Platform, RegistryError

ADMIN_PATH = f"/admin/realms/{platforms.REALM}"
BACKEND_DIR = Path(__file__).resolve().parents[3]
# The single source of the corporate provider rules (G-160). The command loads the file by path and
# does not import the platform_core package.
RULES_PATH = BACKEND_DIR / "apps" / "platform_core" / "platform_core" / "identity" / "enterprise_rules.py"
# Generic provider types. Every other type in the registry is a social platform type.
GENERIC_PROVIDER_IDS = frozenset({"oidc", "keycloak-oidc", "saml"})
EXCEPTION_ACTION = "not-in-registry-exception"


class ApplyError(RuntimeError):
    """The apply step cannot continue safely. The message never holds a secret.

    ``rule`` names the broken rule when the error comes from a corporate provider check.
    """

    def __init__(self, message: str, rule: str | None = None):
        super().__init__(message)
        self.rule = rule


def _refused(alias: str, rule: str) -> ApplyError:
    return ApplyError(f"Corporate provider {alias} refused: {rule}.", rule)


def load_enterprise_rules(path: Path | None = None) -> ModuleType:
    """Load enterprise_rules.py by its path. A missing file stops the command."""
    path = RULES_PATH if path is None else path
    if not path.is_file():
        raise ApplyError("The corporate provider rules file is missing: rules_missing.", "rules_missing")
    spec = importlib.util.spec_from_file_location("atonota_enterprise_rules", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_exceptions(path: Path) -> list[dict]:
    """Read the exceptions file that the sync step writes. One record per provider alias."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ApplyError("The exceptions file cannot be read as JSON.", "invalid_exceptions_file") from None
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ApplyError("The exceptions file must hold a list of records.", "invalid_exceptions_file")
    aliases = [item.get("provider_alias") for item in value]
    for alias in aliases:
        if not isinstance(alias, str) or aliases.count(alias) > 1:
            raise ApplyError("The exceptions file must name each provider once: duplicate_provider.",
                             "duplicate_provider")
    return value


def social_names(registry: Sequence[Platform], rules: ModuleType | None = None) -> tuple[set[str], set[str]]:
    """Aliases and provider types of the social platforms. They never take an exception.

    The names come from the registry, the product's platforms folder and the rules module.
    """
    found = list(registry)
    if platforms.REGISTRY_DIR.is_dir():
        found += platforms.load_platforms(platforms.REGISTRY_DIR)
    aliases = {platform.alias for platform in found}
    provider_ids = {platform.provider_id for platform in found} - GENERIC_PROVIDER_IDS
    if rules is not None:
        aliases |= set(rules.SOCIAL_PROVIDER_ALIASES)
        provider_ids |= set(rules.SOCIAL_PROVIDER_IDS)
    return aliases, provider_ids


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _resolves_to_loopback(host: str) -> bool:
    try:
        found = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(found) and all(ipaddress.ip_address(entry[4][0]).is_loopback for entry in found)


def checked_keycloak_url(url: str, expected_remote_host: str | None = None) -> str:
    parts = urllib.parse.urlsplit(url.rstrip("/"))
    host = parts.hostname or ""
    if parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ApplyError("The Keycloak address must be scheme, host and port only.")
    if platforms.LOCAL_HOST.fullmatch(host) and parts.scheme in ("http", "https"):
        # The admin password goes over plain http only to this machine.
        if not _resolves_to_loopback(host):
            raise ApplyError("The local Keycloak name does not resolve to this machine.")
        return f"{parts.scheme}://{parts.netloc}"
    if expected_remote_host is None:
        raise ApplyError("Only a local Keycloak is accepted. Pass --remote-host for an approved remote change.")
    if parts.scheme != "https" or host != expected_remote_host or parts.port not in (None, 443):
        raise ApplyError("A remote Keycloak must use https and match --remote-host exactly.")
    return f"https://{host}"


def admin_caller(keycloak_url: str, username: str, password: str) -> Callable:
    """Return call(method, path, payload) -> (status, json or None) for the platform realm."""
    opener = urllib.request.build_opener(_NoRedirect())

    def send(method, url, data, headers):
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(request, timeout=30) as response:
                return response.status, response.read(8 << 20)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            return status, b""

    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "admin-cli", "username": username, "password": password}
    ).encode()
    status, body = send(
        "POST", f"{keycloak_url}/realms/master/protocol/openid-connect/token", form,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status != 200:
        raise ApplyError(f"Keycloak admin sign-in failed. HTTP {status}.")
    token = json.loads(body)["access_token"]

    def call(method, path, payload=None):
        status, body = send(
            method, f"{keycloak_url}{ADMIN_PATH}{path}",
            json.dumps(payload).encode() if payload is not None else None,
            {"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        return status, (json.loads(body) if body else None)

    return call


def _quoted(alias: str) -> str:
    return urllib.parse.quote(alias, safe="")


def apply_registry(
    call: Callable,
    registry: list[Platform],
    environment: Mapping[str, str],
    *,
    exceptions: Sequence[Mapping] = (),
    rules: ModuleType | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Bring every registry platform to its desired state, then check the other providers.

    Returns one report line per provider. ``exceptions`` comes from read_exceptions and ``rules``
    from load_enterprise_rules. ``now`` is the clock for the expiry check; tests pass a fixed one.
    """
    report = []
    for platform in registry:
        state = platforms.desired_state(platform, environment)
        path = f"/identity-provider/instances/{_quoted(platform.alias)}"
        status, current = call("GET", path)
        if status == 404:
            status, _ = call("POST", "/identity-provider/instances", state)
            action = "created"
        elif status == 200:
            kept = {k: v for k, v in (current.get("config") or {}).items() if k not in platform.secrets}
            merged = {**current, **state, "config": {**kept, **state["config"]}}
            status, _ = call("PUT", path, merged)
            action = "updated"
        else:
            raise ApplyError(f"Reading platform {platform.alias} failed. HTTP {status}.")
        if status not in (200, 201, 204):
            raise ApplyError(f"Writing platform {platform.alias} failed. HTTP {status}.")
        report.append({"alias": platform.alias, "action": action, "enabled": state["enabled"]})
    status, existing = call("GET", "/identity-provider/instances")
    if status != 200:
        raise ApplyError(f"Listing identity providers failed. HTTP {status}.")
    known = {platform.alias for platform in registry}
    by_alias = {item.get("provider_alias"): item for item in exceptions}
    social = None
    for provider in existing or []:
        if provider["alias"] not in known:
            if social is None:
                social = social_names(registry, rules)
            report.append(_check_corporate(provider, by_alias, social, rules, now))
    return report


def _is_on(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _check_corporate(provider: Mapping, by_alias: Mapping, social: tuple, rules, now) -> dict:
    """Check one provider outside the registry in the order of the design (AJA-238, section 5).

    The provider is not changed. Every break raises ApplyError and stops the command.
    """
    alias = provider["alias"]
    # Keycloak may return "config": null (review 2, finding 1).
    config = provider.get("config") or {}
    line = {"alias": alias, "action": "not-in-registry", "enabled": provider.get("enabled")}
    # 1. trustEmail comes before the exception: no exception allows it.
    if _is_on(provider.get("trustEmail")) or _is_on(config.get("trustEmail")):
        raise _refused(alias, "trust_email")
    # 2. A provider with the email_verified rule needs no exception.
    if not all(config.get(k) == v for k, v in platforms.VERIFIED_EMAIL_CLAIM.items()):
        # 3. Without the rule a valid exception record is required. A warning is not enough.
        record = by_alias.get(alias)
        if record is None:
            raise _refused(alias, "missing_exception")
        # 4. Social platforms never take the exception.
        social_aliases, social_provider_ids = social
        if alias in social_aliases or provider.get("providerId") in social_provider_ids:
            raise _refused(alias, "social_platform")
        if rules is None:
            raise _refused(alias, "rules_missing")
        # 5. Every rule of the record.
        try:
            checked = rules.check_record(record, social_aliases=social_aliases)
        except rules.EnterpriseRuleError as error:
            raise _refused(alias, error.rule) from None
        if checked["kind"] != "grant":
            raise _refused(alias, "revoked")
        # 6. The record is for this provider's issuer.
        if config.get("issuer") != checked["issuer"]:
            raise _refused(alias, "issuer_mismatch")
        # 7. The expiry date, against the given clock.
        moment = now if now is not None else datetime.now(timezone.utc)
        if rules.is_expired(record, moment):
            raise _refused(alias, "expired")
        line.update({"action": EXCEPTION_ACTION, "exception": checked["name"]})
    # 8. The shared broker flows keep the linking rule and the enterprise-sso-required check.
    if (provider.get("firstBrokerLoginFlowAlias") != platforms.FIRST_BROKER_FLOW
            or provider.get("postBrokerLoginFlowAlias") != platforms.POST_BROKER_FLOW):
        raise _refused(alias, "broker_flow")
    # 9. One report line per provider.
    return line


__all__ = [
    "ApplyError",
    "RegistryError",
    "admin_caller",
    "apply_registry",
    "checked_keycloak_url",
    "load_enterprise_rules",
    "read_exceptions",
]
