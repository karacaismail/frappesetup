"""Create the synthetic Keycloak account and the read-only client of the deletion chain test.

Runs inside the stack network with `python -I`. Input on stdin: keycloak_url, admin_username,
admin_password, identity_sync_secret, email, password. Output on stdout: subject, reader_client,
reader_secret and a short-lived service_token of the sync service for the direct O-44 check.
It accepts only a plain-HTTP local development Keycloak and prints no secret.
"""

import http.client
import json
import re
import secrets
import sys
import urllib.parse

REALM = "platform"
READER_CLIENT = "e2e-stack-reader"
SYNC_CLIENT = "identity-sync"
TENANT_SCOPE = "aud-site-tenant1"
LOCAL_HOST = re.compile(r"(?:localhost|127\.0\.0\.1|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.localhost)")


class Keycloak:
    """Plain HTTP to one local Keycloak host. The address is checked once, in `main`."""

    def __init__(self, base_url):
        parts = urllib.parse.urlsplit(base_url)
        self._host, self._port = parts.hostname, parts.port or 80
        self._token = None

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(self._host, self._port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            raw = response.read()
            return response.status, response.getheader("Location"), raw
        finally:
            connection.close()

    def token(self, realm, form):
        status, _, raw = self.request(
            "POST",
            f"/realms/{realm}/protocol/openid-connect/token",
            urllib.parse.urlencode(form),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status != 200:
            raise SystemExit(f"Keycloak refused the {form['client_id']} token request (HTTP {status}).")
        token = json.loads(raw).get("access_token")
        if not isinstance(token, str) or not token:
            raise SystemExit(f"Keycloak returned no {form['client_id']} access token.")
        return token

    def sign_in(self, username, password):
        self._token = self.token(
            "master", {"grant_type": "password", "client_id": "admin-cli", "username": username, "password": password}
        )

    def call(self, path, *, method=None, data=None):
        body = None if data is None else json.dumps(data)
        status, location, raw = self.request(
            method or ("POST" if data is not None else "GET"),
            f"/admin/realms/{REALM}{path}",
            body,
            {"Authorization": "Bearer " + self._token, "Content-Type": "application/json"},
        )
        return status, location, (json.loads(raw) if raw else None)

    def expect(self, expected, what, path, **kwargs):
        status, location, data = self.call(path, **kwargs)
        if status not in expected:
            raise SystemExit(f"Keycloak did not {what} (HTTP {status}).")
        return location, data


def create_user(keycloak, email, password):
    _, found = keycloak.expect({200}, "search users", "/users?exact=true&email=" + urllib.parse.quote(email))
    if found:
        raise SystemExit("The synthetic deletion account already exists. Use a new run.")
    location, _ = keycloak.expect(
        {201},
        "create the user",
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
    if not location:
        raise SystemExit("Keycloak did not name the created user.")
    return location.rsplit("/", 1)[-1]


def ensure_reader(keycloak):
    """A service-account client that may only read users.

    The scopes and the `view-users` role are applied on every seed, so a kept database with an
    older client gets them too. The secret is renewed on every seed.
    """
    _, scopes = keycloak.expect({200}, "list client scopes", "/client-scopes")
    scope_ids = {scope["name"]: scope["id"] for scope in scopes}
    _, existing = keycloak.expect({200}, "find the reader client", "/clients?clientId=" + READER_CLIENT)
    if existing:
        reader = existing[0]
        _, renewed = keycloak.expect({200}, "renew the reader secret", f"/clients/{reader['id']}/client-secret", data={})
        secret = renewed.get("value") if isinstance(renewed, dict) else None
        if not secret:
            raise SystemExit("Keycloak returned no renewed reader secret.")
    else:
        secret = secrets.token_urlsafe(32)
        keycloak.expect(
            {201},
            "create the reader client",
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
        _, (reader,) = keycloak.expect({200}, "find the reader client", "/clients?clientId=" + READER_CLIENT)
    for scope in ("basic", "service_account", "kc-admin-api"):
        keycloak.expect(
            {204}, f"bind the {scope} scope", f"/clients/{reader['id']}/default-client-scopes/{scope_ids[scope]}",
            method="PUT", data={},
        )
    _, (management,) = keycloak.expect({200}, "find realm-management", "/clients?clientId=realm-management")
    _, service_user = keycloak.expect({200}, "read the service account", f"/clients/{reader['id']}/service-account-user")
    _, role = keycloak.expect({200}, "read the view-users role", f"/clients/{management['id']}/roles/view-users")
    keycloak.expect(
        {204}, "grant view-users to the service account",
        f"/users/{service_user['id']}/role-mappings/clients/{management['id']}", data=[role],
    )
    keycloak.expect(
        {204}, "allow view-users in the reader token",
        f"/clients/{reader['id']}/scope-mappings/clients/{management['id']}", data=[role],
    )
    return secret


def main():
    payload = json.load(sys.stdin)
    base_url = payload["keycloak_url"]
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme != "http" or not LOCAL_HOST.fullmatch(parts.hostname or "") or parts.path not in ("", "/"):
        raise SystemExit("Only a local development Keycloak is accepted.")
    email = payload["email"]
    if not re.fullmatch(r"e2e-delete-[a-z0-9]+@example\.test", email):
        raise SystemExit("The deletion fixture needs a dedicated synthetic address.")
    keycloak = Keycloak(base_url)
    keycloak.sign_in(payload["admin_username"], payload["admin_password"])
    subject = create_user(keycloak, email, payload["password"])
    reader_secret = ensure_reader(keycloak)
    # The test repeats the sync service's tenant call with this token to read the O-44 reply itself.
    # The token lives as long as the realm's access token lifespan (300 seconds).
    service_token = keycloak.token(
        REALM,
        {
            "grant_type": "client_credentials",
            "client_id": SYNC_CLIENT,
            "client_secret": payload["identity_sync_secret"],
            "scope": TENANT_SCOPE,
        },
    )
    print(json.dumps({
        "subject": subject, "reader_client": READER_CLIENT, "reader_secret": reader_secret,
        "service_token": service_token,
    }))


if __name__ == "__main__":
    main()
