"""Create the synthetic Keycloak account and the read-only client of the deletion chain test.

Runs inside the stack network with `python -I`. Input on stdin: keycloak_url, admin_username,
admin_password, email, password. Output on stdout: subject, reader_client, reader_secret.
It accepts only a local development Keycloak and prints no secret.
"""

import json
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

REALM = "platform"
READER_CLIENT = "e2e-stack-reader"
LOCAL_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.localhost)")


class Keycloak:
    def __init__(self, base_url, token):
        self._base = base_url.rstrip("/") + f"/admin/realms/{REALM}"
        self._token = token

    def call(self, path, *, method=None, data=None):
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(
            self._base + path,
            data=body,
            method=method or ("POST" if data is not None else "GET"),
            headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                return response.status, response.headers.get("Location"), (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as error:
            error.read()
            return error.code, None, None


def admin_token(base_url, username, password):
    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "admin-cli", "username": username, "password": password}
    ).encode()
    with urllib.request.urlopen(
        base_url.rstrip("/") + "/realms/master/protocol/openid-connect/token", form, timeout=20
    ) as response:
        return json.load(response)["access_token"]


def created_id(status, location, what):
    if status != 201 or not location:
        raise SystemExit(f"Keycloak did not create the {what} (HTTP {status}).")
    return location.rsplit("/", 1)[-1]


def create_user(keycloak, email, password):
    status, _, found = keycloak.call("/users?exact=true&email=" + urllib.parse.quote(email))
    if status == 200 and found:
        raise SystemExit("The synthetic deletion account already exists. Use a new run.")
    status, location, _ = keycloak.call(
        "/users",
        data={
            "username": email,
            "email": email,
            "emailVerified": True,
            "enabled": True,
            "firstName": "Synthetic",
            "lastName": "Deletion",
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        },
    )
    return created_id(status, location, "user")


def ensure_reader(keycloak):
    """A service-account client that may only read users. Its secret is renewed on every seed."""
    secret = secrets.token_urlsafe(32)
    status, _, scopes = keycloak.call("/client-scopes")
    if status != 200:
        raise SystemExit(f"Keycloak client scopes are not readable (HTTP {status}).")
    scope_ids = {scope["name"]: scope["id"] for scope in scopes}
    status, _, existing = keycloak.call("/clients?clientId=" + READER_CLIENT)
    if status == 200 and existing:
        status, _, renewed = keycloak.call(f"/clients/{existing[0]['id']}/client-secret", data={})
        if status != 200 or not isinstance(renewed, dict) or not renewed.get("value"):
            raise SystemExit(f"Keycloak did not renew the reader client secret (HTTP {status}).")
        return renewed["value"]
    status, _, _ = keycloak.call(
        "/clients",
        data={
            "clientId": READER_CLIENT,
            "protocol": "openid-connect",
            "enabled": True,
            "publicClient": False,
            "secret": secret,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "fullScopeAllowed": False,
            "defaultClientScopes": ["roles"],
        },
    )
    if status != 201:
        raise SystemExit(f"Keycloak did not create the reader client (HTTP {status}).")
    (reader,) = keycloak.call("/clients?clientId=" + READER_CLIENT)[2]
    for scope in ("basic", "service_account", "kc-admin-api"):
        keycloak.call(f"/clients/{reader['id']}/default-client-scopes/{scope_ids[scope]}", method="PUT", data={})
    (management,) = keycloak.call("/clients?clientId=realm-management")[2]
    service_user = keycloak.call(f"/clients/{reader['id']}/service-account-user")[2]
    role = keycloak.call(f"/clients/{management['id']}/roles/view-users")[2]
    keycloak.call(f"/users/{service_user['id']}/role-mappings/clients/{management['id']}", data=[role])
    keycloak.call(f"/clients/{reader['id']}/scope-mappings/clients/{management['id']}", data=[role])
    return secret


def main():
    payload = json.load(sys.stdin)
    base_url = payload["keycloak_url"]
    host = urllib.parse.urlsplit(base_url).hostname or ""
    if urllib.parse.urlsplit(base_url).scheme != "http" or not LOCAL_HOST.fullmatch(host):
        raise SystemExit("Only a local development Keycloak is accepted.")
    email = payload["email"]
    if not re.fullmatch(r"e2e-delete-[a-z0-9]+@example\.test", email):
        raise SystemExit("The deletion fixture needs a dedicated synthetic address.")
    keycloak = Keycloak(base_url, admin_token(base_url, payload["admin_username"], payload["admin_password"]))
    subject = create_user(keycloak, email, payload["password"])
    reader_secret = ensure_reader(keycloak)
    print(json.dumps({"subject": subject, "reader_client": READER_CLIENT, "reader_secret": reader_secret}))


if __name__ == "__main__":
    main()
