#!/usr/bin/env python3
"""Apply the realm file's clients and client scopes to a kept development Keycloak database.

Keycloak's --import-realm skips a realm that already exists. A kept development database then keeps
old clients and scopes (MVP test 2, finding T-11). This command closes that gap and can run again.

- It only adds and corrects. It never deletes clients, scopes, users or sessions.
  It removes a scope binding only to move it to the category the realm file names.
- It accepts only a local development Keycloak (localhost, 127.0.0.1 or a *.localhost name).
  A production realm change is a separate, approved task (identity/keycloak/README.md).
- It prints names of changed items, never a secret.

Usage:
  sync-dev-realm.py --stdin     JSON on stdin: keycloak_url, realm, values, admin_username, admin_password
  sync-dev-realm.py --from-env  realm file from the repository; values from the environment
"""

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REALM = "platform"
ADMIN_PATH = f"/admin/realms/{REALM}"
# The parts of the realm file this command applies.
SYNCED_KEYS = (
    "clients",
    "clientScopes",
    "defaultDefaultClientScopes",
    "defaultOptionalClientScopes",
    "clientScopeMappings",
)
# Keycloak's import replaces ${NAME} and ${NAME:default}. Message keys such as ${emailScopeConsentText}
# are not environment names: Keycloak leaves them as they are, and so does this command.
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_.]+)(?::([^}]*))?\}")
ENVIRONMENT_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
LOCAL_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.localhost)")
# Client fields that have their own endpoints and must not travel in the client update.
CLIENT_SUBRESOURCES = ("defaultClientScopes", "optionalClientScopes", "protocolMappers")
MAPPER_FIELDS = ("protocol", "protocolMapper", "consentRequired", "config")


class SyncError(Exception):
    """The sync cannot safely continue. The message never holds a secret."""


def resolve(value, values):
    """Replace environment placeholders the way Keycloak's realm import does."""
    if isinstance(value, dict):
        return {key: resolve(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, values) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match):
        name, default = match.group(1), match.group(2)
        if name in values:
            return values[name]
        if default is not None:
            return default
        if ENVIRONMENT_NAME.fullmatch(name):
            raise SyncError(f"The realm file needs the setting {name}.")
        return match.group(0)

    return PLACEHOLDER.sub(replace, value)


def local_keycloak_url(url):
    """Accept only a local development Keycloak origin."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    try:
        parts.port
    except ValueError:
        raise SyncError("The Keycloak address has an invalid port.") from None
    if (
        parts.scheme not in ("http", "https")
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or not LOCAL_HOST.fullmatch(host)
    ):
        raise SyncError("Only a local development Keycloak is accepted. Production changes need approval.")
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def admin_caller(keycloak_url, username, password):
    """Return call(method, path, payload) for the platform realm's Admin API."""
    opener = urllib.request.build_opener(NoRedirect())

    def send(method, url, *, data, headers):
        call = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with opener.open(call, timeout=30) as response:
                body = response.read(8 << 20)
                return response.status, body
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            return status, b""

    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "admin-cli", "username": username, "password": password}
    ).encode()
    status, body = send(
        "POST",
        f"{keycloak_url}/realms/master/protocol/openid-connect/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status != 200:
        raise SyncError(f"Keycloak admin sign-in failed. HTTP {status}.")
    token = json.loads(body)["access_token"]

    def call(method, path, payload=None):
        status, body = send(
            method,
            f"{keycloak_url}{ADMIN_PATH}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        if status not in (200, 201, 204):
            # The path holds only names and internal IDs, never a secret.
            raise SyncError(f"{method} {urllib.parse.urlsplit(path).path} failed. HTTP {status}.")
        return json.loads(body) if body else None

    return call


def same(wanted, actual):
    """True when every value the realm file names is already in Keycloak."""
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(same(value, actual.get(key)) for key, value in wanted.items())
    if isinstance(wanted, list) and all(isinstance(item, str) for item in wanted):
        return isinstance(actual, list) and sorted(wanted) == sorted(actual)
    return wanted == actual


def quoted(value):
    return urllib.parse.quote(value, safe="")


def sync_mappers(call, owner_path, wanted, label, changes):
    if not wanted:
        return
    existing = {mapper["name"]: mapper for mapper in call("GET", f"{owner_path}/protocol-mappers/models")}
    for mapper in wanted:
        current = existing.get(mapper["name"])
        if current is None:
            call("POST", f"{owner_path}/protocol-mappers/models", mapper)
            changes.append(f"{label}: mapper {mapper['name']} added")
        elif not same({key: mapper[key] for key in MAPPER_FIELDS if key in mapper}, current):
            updated = dict(copy.deepcopy(current), **copy.deepcopy(mapper), id=current["id"])
            call("PUT", f"{owner_path}/protocol-mappers/models/{quoted(current['id'])}", updated)
            changes.append(f"{label}: mapper {mapper['name']} updated")


def sync_scopes(call, scopes, changes):
    existing = {scope["name"]: scope for scope in call("GET", "/client-scopes")}
    for scope in scopes:
        name = scope["name"]
        current = existing.get(name)
        if current is None:
            call("POST", "/client-scopes", scope)
            changes.append(f"client scope {name}: created")
            continue
        fields = {key: value for key, value in scope.items() if key != "protocolMappers"}
        if not same(fields, current):
            updated = copy.deepcopy(current)
            updated.update(copy.deepcopy(fields))
            updated["attributes"] = dict(current.get("attributes") or {}, **fields.get("attributes", {}))
            updated["id"] = current["id"]
            updated.pop("protocolMappers", None)
            call("PUT", f"/client-scopes/{quoted(current['id'])}", updated)
            changes.append(f"client scope {name}: settings updated")
        sync_mappers(call, f"/client-scopes/{quoted(current['id'])}", scope.get("protocolMappers"),
                     f"client scope {name}", changes)
    return {scope["name"]: scope["id"] for scope in call("GET", "/client-scopes")}


def find_client(call, client_id):
    query = urllib.parse.urlencode({"clientId": client_id, "search": "false"})
    return next((client for client in call("GET", f"/clients?{query}") if client["clientId"] == client_id), None)


def sync_bindings(call, client_path, client, scope_ids, label, changes):
    wanted = {
        "default": set(client.get("defaultClientScopes", [])),
        "optional": set(client.get("optionalClientScopes", [])),
    }
    bound = {
        kind: {scope["name"]: scope["id"] for scope in call("GET", f"{client_path}/{kind}-client-scopes")}
        for kind in wanted
    }
    for kind, other in (("default", "optional"), ("optional", "default")):
        for name in sorted(wanted[kind]):
            if name in bound[kind]:
                continue
            if name not in scope_ids:
                raise SyncError(f"{label}: client scope {name} is missing in Keycloak.")
            if name in bound[other]:
                # Keycloak keeps one category per binding: move it to the one the realm file names.
                call("DELETE", f"{client_path}/{other}-client-scopes/{quoted(bound[other].pop(name))}")
            call("PUT", f"{client_path}/{kind}-client-scopes/{quoted(scope_ids[name])}")
            changes.append(f"{label}: {kind} scope {name} added")


def sync_clients(call, clients, scope_ids, changes):
    for client in clients:
        client_id = client["clientId"]
        label = f"client {client_id}"
        current = find_client(call, client_id)
        if current is None:
            call("POST", "/clients", client)
            changes.append(f"{label}: created")
            current = find_client(call, client_id)
            if current is None:
                raise SyncError(f"{label}: Keycloak did not create the client.")
        fields = {key: value for key, value in client.items() if key not in CLIENT_SUBRESOURCES}
        client_path = f"/clients/{quoted(current['id'])}"
        detail = call("GET", client_path)
        if not same(fields, detail):
            updated = copy.deepcopy(detail)
            for key in CLIENT_SUBRESOURCES:
                updated.pop(key, None)
            updated.update(copy.deepcopy(fields))
            updated["attributes"] = dict(detail.get("attributes") or {}, **fields.get("attributes", {}))
            updated["id"] = current["id"]
            call("PUT", client_path, updated)
            # Only field names: a changed secret is reported as "secret", never its value.
            changed = sorted(key for key, value in fields.items() if not same(value, detail.get(key)))
            changes.append(f"{label}: updated {', '.join(changed)}")
        sync_mappers(call, client_path, client.get("protocolMappers"), label, changes)
        sync_bindings(call, client_path, client, scope_ids, label, changes)


def sync_realm_defaults(call, realm, scope_ids, changes):
    for kind, key in (("default", "defaultDefaultClientScopes"), ("optional", "defaultOptionalClientScopes")):
        path = f"/default-{kind}-client-scopes"
        present = {scope["name"] for scope in call("GET", path)}
        for name in realm.get(key, []):
            if name not in present and name in scope_ids:
                call("PUT", f"{path}/{quoted(scope_ids[name])}")
                changes.append(f"realm: {kind} client scope {name} added")


def sync_scope_role_mappings(call, realm, scope_ids, changes):
    for client_id, mappings in realm.get("clientScopeMappings", {}).items():
        client = find_client(call, client_id)
        if client is None:
            raise SyncError(f"client {client_id} is missing in Keycloak.")
        for mapping in mappings:
            scope = mapping["clientScope"]
            path = f"/client-scopes/{quoted(scope_ids[scope])}/scope-mappings/clients/{quoted(client['id'])}"
            present = {role["name"] for role in call("GET", path)}
            missing = [name for name in mapping["roles"] if name not in present]
            if missing:
                roles = [call("GET", f"/clients/{quoted(client['id'])}/roles/{quoted(name)}") for name in missing]
                call("POST", path, roles)
                changes.append(f"client scope {scope}: {client_id} roles {', '.join(missing)} added")


def sync_realm(realm, call):
    """Apply the resolved realm parts to Keycloak. Returns the list of changes, without secrets."""
    changes = []
    scope_ids = sync_scopes(call, realm.get("clientScopes", []), changes)
    sync_clients(call, realm.get("clients", []), scope_ids, changes)
    sync_realm_defaults(call, realm, scope_ids, changes)
    sync_scope_role_mappings(call, realm, scope_ids, changes)
    return changes


def load_request(arguments, stdin):
    if arguments.stdin:
        payload = json.load(stdin)
        return (payload["keycloak_url"], payload["realm"], payload["values"],
                payload["admin_username"], payload["admin_password"])
    # The stack sends this file's text with "python -c"; only --from-env needs the repository path.
    realm_file = Path(__file__).resolve().parents[1] / "realm" / "platform-realm.json"
    realm = json.loads(realm_file.read_text(encoding="utf-8"))
    values = dict(os.environ)
    for name in ("KC_PUBLIC_URL", "KC_BOOTSTRAP_ADMIN_USERNAME", "KC_BOOTSTRAP_ADMIN_PASSWORD"):
        if not values.get(name):
            raise SyncError(f"Set {name}.")
    return (values["KC_PUBLIC_URL"], realm, values,
            values["KC_BOOTSTRAP_ADMIN_USERNAME"], values["KC_BOOTSTRAP_ADMIN_PASSWORD"])


def main(argv=None, stdin=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stdin", action="store_true", help="read the request as JSON on stdin")
    source.add_argument("--from-env", action="store_true", help="read the realm file and the environment")
    arguments = parser.parse_args(argv)
    try:
        url, realm, values, username, password = load_request(arguments, stdin or sys.stdin)
        url = local_keycloak_url(url.rstrip("/"))
        parts = resolve({key: realm[key] for key in SYNCED_KEYS if key in realm}, values)
        changes = sync_realm(parts, admin_caller(url, username, password))
    except (SyncError, KeyError, ValueError) as error:
        message = str(error) if isinstance(error, SyncError) else f"Invalid request: {type(error).__name__}."
        print(f"Realm sync refused: {message}", file=sys.stderr)
        return 2
    except OSError:
        print("Realm sync failed: Keycloak could not be reached.", file=sys.stderr)
        return 1
    for change in changes:
        print(f"Realm sync: {change}")
    print(f"Realm sync: {len(changes)} change(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
