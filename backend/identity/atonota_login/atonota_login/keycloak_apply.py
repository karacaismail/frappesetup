# SPDX-License-Identifier: MIT
"""Apply the platform registry to a running Keycloak through its Admin API (G-159).

Keycloak's realm import cannot open a platform only when its secret exists. This command does
that step and can run again:

- A platform whose secrets are all set opens and shows on the login page.
- A platform with a missing secret, or with ``"active": false``, is closed and hidden. Its stored
  secrets are cleared.
- Identity providers that are not in the registry stay as they are. Corporate providers of an
  organization are such providers. The command only lists them.
- Nothing is deleted. No secret is printed.

By default only a local development Keycloak is accepted. A remote Keycloak needs https and an
explicit expected host, so the command cannot reach a wrong environment by mistake.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Mapping

from atonota_login import platforms
from atonota_login.platforms import Platform, RegistryError

ADMIN_PATH = f"/admin/realms/{platforms.REALM}"


class ApplyError(RuntimeError):
    """The apply step cannot continue safely. The message never holds a secret."""


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


def apply_registry(call: Callable, registry: list[Platform], environment: Mapping[str, str]) -> list[dict]:
    """Bring every registry platform to its desired state. Returns one report line per platform."""
    report = []
    for platform in registry:
        state = platforms.desired_state(platform, environment)
        path = f"/identity-provider/instances/{_quoted(platform.alias)}"
        status, current = call("GET", path)
        if status == 404:
            status, _ = call("POST", "/identity-provider/instances", state)
            action = "created"
        elif status == 200:
            kept = {k: v for k, v in current.get("config", {}).items() if k not in platform.secrets}
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
    for provider in existing or []:
        if provider["alias"] not in known:
            report.append({"alias": provider["alias"], "action": "not-in-registry", "enabled": provider.get("enabled")})
    return report


__all__ = ["ApplyError", "RegistryError", "admin_caller", "apply_registry", "checked_keycloak_url"]
