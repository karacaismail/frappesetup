#!/usr/bin/env python3
"""Preview and create a tenant client using a human operator's Keycloak token."""

import argparse
import getpass
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
    client = next(client for client in realm["clients"] if client.get("clientId") == "site-kiraci1")
    client.pop("secret")
    client["clientId"] = f"site-{slug}"
    client["name"] = f"Tenant site {slug}"
    # The template lists the login, panel and logout URLs alongside the rest of the tenant policy.
    return json.dumps(client).replace("${ATONOTA_SITE_KIRACI1_URL}", site_url).encode("utf-8")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant", help="Tenant slug, for example acme")
    parser.add_argument("site_url", type=https_origin, help="Tenant site HTTPS origin")
    parser.add_argument("keycloak_url", type=https_origin, help="Keycloak HTTPS origin")
    parser.add_argument("--preview", action="store_true", help="Show the request without creating the client")
    args = parser.parse_args()
    if len(args.tenant) > 63 or not TENANT_SLUG.fullmatch(args.tenant):
        parser.error("Use up to 63 lowercase letters, digits, and single hyphens for the tenant slug.")

    client_id = f"site-{args.tenant}"
    endpoint = f"{args.keycloak_url}/admin/realms/platform/clients"
    body = tenant_client(args.tenant, args.site_url)
    print(f"POST {endpoint}")
    print(json.dumps(json.loads(body), indent=2))
    if args.preview:
        return 0
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        print("Creation requires an interactive terminal.", file=sys.stderr)
        return 2

    confirmation = f"CREATE {client_id}"
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

    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except (OSError, ValueError):
        print("Keycloak request failed. Check the client list before retrying.", file=sys.stderr)
        return 1
    if status == 409:
        print(f"HTTP 409. {client_id} already exists.", file=sys.stderr)
        return 1
    if status != 201:
        print(f"Client creation failed. HTTP {status}.", file=sys.stderr)
        return 1
    print(f"Created {client_id}. HTTP 201.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
