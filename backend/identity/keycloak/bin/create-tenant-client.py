#!/usr/bin/env python3
"""Preview and create a tenant client using a human operator's Keycloak token."""

import argparse
import getpass
import itertools
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

REALM_FILE = Path(__file__).resolve().parents[1] / "realm" / "platform-realm.json"
HTTPS_ORIGIN = re.compile(r"https://[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]{1,5})?/?")
TENANT_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SERVICE_CLIENTS = ("identity-sync", "press-service")
ADMIN_PATH = "/admin/realms/platform"
LOGOUT_ATTRIBUTE = "post.logout.redirect.uris"


def https_origin(value):
    if not HTTPS_ORIGIN.fullmatch(value):
        raise argparse.ArgumentTypeError("Enter an HTTPS origin without a path, credentials, or wildcard.")
    origin = value.rstrip("/")
    try:
        port = urllib.parse.urlsplit(origin).port
    except ValueError:
        port = 0
    if port == 0:
        raise argparse.ArgumentTypeError("Enter a port between 1 and 65535.")
    return origin


def tenant_client(slug, site_url):
    realm = json.loads(REALM_FILE.read_text(encoding="utf-8"))
    client = next(client for client in realm["clients"] if client.get("clientId") == "site-tenant1")
    client.pop("secret")
    client["clientId"] = f"site-{slug}"
    client["name"] = f"Tenant site {slug}"
    # The template lists the login, panel and logout URLs alongside the rest of the tenant policy.
    return json.loads(json.dumps(client).replace("${ATONOTA_SITE_TENANT1_URL}", site_url))


def tenant_service_client(slug):
    realm = json.loads(REALM_FILE.read_text(encoding="utf-8"))
    client = next(client for client in realm["clients"] if client["clientId"] == "site-tenant1-service")
    client.pop("secret")
    client["clientId"] = f"site-{slug}-service"
    client["name"] = f"Tenant service {slug}"
    return client


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProvisioningError(Exception):
    """An operation cannot safely continue."""


def tenant_scope(client_id):
    realm = json.loads(REALM_FILE.read_text(encoding="utf-8"))
    scope = next(scope for scope in realm["clientScopes"] if scope["name"] == "aud-site-tenant1")
    return json.loads(json.dumps(scope).replace("site-tenant1", client_id))


def make_admin_request(keycloak_url, token):
    opener = urllib.request.build_opener(NoRedirect())

    def request(method, path, *, payload=None, expected=(200,)):
        call = urllib.request.Request(
            f"{keycloak_url}{ADMIN_PATH}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method=method,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        try:
            with opener.open(call, timeout=15) as response:
                status = response.status
                if status == 200 and status in expected:
                    limit = 1 << 20
                    body = response.read(limit + 1)
                    if len(body) > limit:
                        raise ProvisioningError("Keycloak returned more than 1 MiB.")
                    return json.loads(body)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
        if status not in expected:
            raise ProvisioningError(f"{method} {path} failed. HTTP {status}.")
        return None

    return request


def find_client(request, name):
    query = urllib.parse.urlencode({"clientId": name, "search": "false"})
    return next((client for client in request("GET", f"/clients?{query}") if client["clientId"] == name), None)


def check_other_bindings(request, scope_name):
    page_size = 100
    for first in itertools.count(0, page_size):
        clients = request("GET", f"/clients?first={first}&max={page_size}")
        for client in clients:
            name = client["clientId"]
            in_default = scope_name in (client.get("defaultClientScopes") or [])
            in_optional = scope_name in (client.get("optionalClientScopes") or [])
            if in_default or (in_optional and name not in SERVICE_CLIENTS):
                raise ProvisioningError(f"Scope {scope_name} has an unexpected binding on {name}.")
        if len(clients) < page_size:
            return


def redirect_addresses(representation):
    """The login callback list and the Keycloak `##`-joined logout return list of a client."""
    attributes = representation.get("attributes") or {}
    logout = [address for address in (attributes.get(LOGOUT_ATTRIBUTE) or "").split("##") if address]
    return {"redirectUris": list(representation.get("redirectUris") or []), LOGOUT_ATTRIBUTE: logout}


def plan_client_update(existing, client, update_redirects):
    """Validate a stored client and prepare any authorized redirect update."""
    client_id = client["clientId"]
    configuration = (
        "protocol",
        "publicClient",
        "clientAuthenticatorType",
        "rootUrl",
        "standardFlowEnabled",
        "directAccessGrantsEnabled",
        "implicitFlowEnabled",
        "fullScopeAllowed",
        "serviceAccountsEnabled",
        "enabled",
    )
    security_attributes = (
        (
            "pkce.code.challenge.method",
            "backchannel.logout.url",
            "backchannel.logout.session.required",
        )
        if client["standardFlowEnabled"]
        else ()
    )
    if (
        existing is None
        or any(existing.get(key) != client.get(key) for key in configuration)
        or set(existing.get("optionalClientScopes") or []) != set(client["optionalClientScopes"])
        or any((existing.get("attributes") or {}).get(key) != client["attributes"][key] for key in security_attributes)
    ):
        raise ProvisioningError(f"Existing client {client_id} does not match the requested tenant.")
    default_scopes = set(existing.get("defaultClientScopes") or [])
    if (
        any(name.startswith("aud-") for name in default_scopes)
        or default_scopes & {"admin-api", "kc-admin-api"}
        or (client["standardFlowEnabled"] and "service_account" in default_scopes)
    ):
        raise ProvisioningError(f"Client {client_id} has an unexpected default service scope.")

    wanted = redirect_addresses(client)
    current = redirect_addresses(existing)
    if any(set(current[key]) - set(wanted[key]) for key in wanted):
        raise ProvisioningError(f"Existing client {client_id} does not match the requested tenant.")
    missing = {key: [address for address in wanted[key] if address not in current[key]] for key in wanted}
    added = [address for addresses in missing.values() for address in addresses]
    if not added:
        return None, []
    if not update_redirects:
        raise ProvisioningError(
            f"Existing client {client_id} is missing redirect addresses: "
            + ", ".join(added)
            + ". Run the command again with --update-redirects to add only these addresses."
        )
    payload = {key: value for key, value in existing.items() if key != "secret"}
    payload["redirectUris"] = current["redirectUris"] + missing["redirectUris"]
    payload["attributes"] = {
        **(existing.get("attributes") or {}),
        LOGOUT_ATTRIBUTE: "##".join(current[LOGOUT_ATTRIBUTE] + missing[LOGOUT_ATTRIBUTE]),
    }
    return payload, added


def validate_scope(request, scope, existing_scope, service_paths):
    scope_name = scope["name"]
    scope_id = urllib.parse.quote(existing_scope["id"], safe="")
    scope_path = f"/client-scopes/{scope_id}"
    mappers = request("GET", f"{scope_path}/protocol-mappers/models")
    (template_mapper,) = scope["protocolMappers"]
    mapper_fields = ("name", "protocol", "protocolMapper")
    # Keycloak 26.8 adds the default UserInfo setting to the stored representation.
    mapper_config = {"userinfo.token.claim": "false", **template_mapper["config"]}
    if (
        existing_scope.get("protocol") != scope["protocol"]
        or existing_scope.get("attributes") != scope["attributes"]
        or len(mappers) != 1
        or any(mappers[0].get(key) != template_mapper[key] for key in mapper_fields)
        or {"userinfo.token.claim": "false", **mappers[0].get("config", {})} != mapper_config
        or any(request("GET", f"{scope_path}/scope-mappings").values())
    ):
        raise ProvisioningError(f"Existing scope {scope_name} does not match the tenant audience template.")

    default_paths = ["/default-default-client-scopes", "/default-optional-client-scopes"]
    default_paths.extend(f"{path}/default-client-scopes" for path in service_paths)
    for path in default_paths:
        if any(item["id"] == existing_scope["id"] for item in request("GET", path)):
            raise ProvisioningError(f"Scope {scope_name} already has a default binding at {path}.")

    return scope_id


def provision_tenant(request, client, scope, service_client, update_redirects=False):
    """Validate existing resources before provisioning and return the addresses added."""
    service_paths = []
    for name in SERVICE_CLIENTS:
        service = find_client(request, name)
        if service is None:
            raise ProvisioningError(f"Required client {name} is missing.")
        service_paths.append(f"/clients/{urllib.parse.quote(service['id'], safe='')}")

    missing_clients = []
    updates = []
    added = []
    for template in (client, service_client):
        existing = find_client(request, template["clientId"])
        if existing is None:
            missing_clients.append(template)
        else:
            payload, addresses = plan_client_update(existing, template, update_redirects)
            if payload is not None:
                updates.append(payload)
                added.extend(addresses)

    scope_name = scope["name"]
    existing_scope = next((item for item in request("GET", "/client-scopes") if item["name"] == scope_name), None)
    scope_id = None
    if existing_scope is not None:
        scope_id = validate_scope(request, scope, existing_scope, service_paths)
    check_other_bindings(request, scope_name)

    for template in missing_clients:
        request("POST", "/clients", payload=template, expected=(201, 409))
        existing = find_client(request, template["clientId"])
        payload, addresses = plan_client_update(existing, template, update_redirects)
        if payload is not None:
            updates.append(payload)
            added.extend(addresses)

    if existing_scope is None:
        request("POST", "/client-scopes", payload=scope, expected=(201, 409))
        existing_scope = next(
            (item for item in request("GET", "/client-scopes") if item["name"] == scope_name),
            None,
        )
        if existing_scope is None:
            raise ProvisioningError(f"Scope {scope_name} was not found after creation.")
        scope_id = validate_scope(request, scope, existing_scope, service_paths)
        check_other_bindings(request, scope_name)

    missing_bindings = []
    for path in service_paths:
        optional_path = f"{path}/optional-client-scopes"
        optional = request("GET", optional_path)
        if not any(item["id"] == existing_scope["id"] for item in optional):
            missing_bindings.append(f"{optional_path}/{scope_id}")

    for path in missing_bindings:
        request("PUT", path, expected=(204,))
    for payload in updates:
        client_path = f"/clients/{urllib.parse.quote(payload['id'], safe='')}"
        request("PUT", client_path, payload=payload, expected=(204,))
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant", help="Tenant slug, for example acme")
    parser.add_argument("site_url", type=https_origin, help="Tenant site HTTPS origin")
    parser.add_argument("keycloak_url", type=https_origin, help="Keycloak HTTPS origin")
    parser.add_argument("--preview", action="store_true", help="Show the request without creating the client")
    parser.add_argument(
        "--update-redirects",
        action="store_true",
        help="Add redirect addresses the template has and an existing client lacks. Change nothing else.",
    )
    args = parser.parse_args()
    if len(args.tenant) > 63 or not TENANT_SLUG.fullmatch(args.tenant):
        parser.error("Use up to 63 lowercase letters, digits, and single hyphens for the tenant slug.")

    client_id = f"site-{args.tenant}"
    if args.tenant.endswith("-service"):
        parser.error("The -service suffix is reserved for service clients.")

    client = tenant_client(args.tenant, args.site_url)
    service_client = tenant_service_client(args.tenant)
    scope = tenant_scope(client_id)
    print(f"Keycloak target: {args.keycloak_url}{ADMIN_PATH}")
    print(
        json.dumps(
            {
                "client": client,
                "service_client": service_client,
                "scope": scope,
                "optional_scope_clients": SERVICE_CLIENTS,
            },
            indent=2,
        )
    )
    if args.preview:
        return 0
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        print("Creation requires an interactive terminal.", file=sys.stderr)
        return 2

    action = "UPDATE" if args.update_redirects else "CREATE"
    confirmation = f"{action} {client_id}"
    try:
        if input(f"Type {confirmation} to continue: ") != confirmation:
            return 2
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Keycloak administrator access token: ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("Creation cancelled.", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token):
        print("Invalid access token format.", file=sys.stderr)
        return 2

    try:
        added = provision_tenant(
            make_admin_request(args.keycloak_url, token), client, scope, service_client, args.update_redirects
        )
    except ProvisioningError as error:
        print(error, file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print("Keycloak request failed. Check the tenant and scope before retrying.", file=sys.stderr)
        return 1
    if added:
        print("Added redirect addresses: " + ", ".join(added))
    print(f"Ready: {client_id}, {service_client['clientId']} and {scope['name']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
