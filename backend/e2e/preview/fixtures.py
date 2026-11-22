"""Create synthetic fixture data in a merge preview's fresh, isolated sites."""

import base64
import http.client
import ipaddress
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote, urlencode

LOGIN_EMAIL = "e2e-user@example.test"
SYNC_EMAIL = "e2e-sync@example.test"
BENCH = "/home/frappe/frappe-bench"
PRESS_BENCH = "/home/frappe/benches/frappe-bench"


def keycloak_request(port, path, *, token=None, data=None, form=False, expect_denial=False):
    headers = {"Host": f"kimlik.localhost:{port}"}
    body = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        body = urlencode(data) if form else json.dumps(data)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("POST" if data is not None else "GET", path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if expect_denial and response.status in (400, 401):
            return json.loads(raw)
        if not 200 <= response.status < 300:
            # Do not print HTTP headers or bodies. They can contain tokens.
            raise RuntimeError(f"Keycloak fixture request returned HTTP {response.status} on {path}")
        return json.loads(raw) if raw else response.getheader("Location")
    finally:
        connection.close()


def check_tenant_clients(port):
    """Exercise the disposable realm without retaining or logging its tokens."""
    path = "/realms/platform/protocol/openid-connect/token"
    browser_secret = os.environ["E2E_KEYCLOAK_CLIENT_SECRET"]
    service_secret = os.environ["E2E_KEYCLOAK_SERVICE_CLIENT_SECRET"]
    if not browser_secret or not service_secret or browser_secret == service_secret:
        raise RuntimeError("The preview requires two distinct tenant client secrets.")

    browser = {
        "grant_type": "client_credentials", "client_id": "site-kiraci1",
        "client_secret": browser_secret,
    }
    for scope in ({}, {"scope": "aud-identity-sync"}):
        response = keycloak_request(port, path, data={**browser, **scope}, form=True, expect_denial=True)
        if not isinstance(response, dict) or response.get("error") not in {"unauthorized_client", "invalid_scope"}:
            raise RuntimeError("The tenant browser client did not refuse the service token request as expected.")

    service_client = "site-kiraci1-service"
    response = keycloak_request(port, path, form=True, data={
        "grant_type": "client_credentials", "client_id": service_client,
        "client_secret": service_secret, "scope": "aud-identity-sync",
    })
    try:
        _, payload, _ = response["access_token"].split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (AttributeError, KeyError, TypeError, ValueError):
        raise RuntimeError("Keycloak returned an invalid preview service token.") from None
    if not isinstance(claims, dict) or claims.get("azp") != service_client or claims.get("aud") not in (
        "identity-sync", ["identity-sync"],
    ):
        raise RuntimeError("The preview service token has an unexpected client or audience.")


def created_identifier(location, fixture_kind):
    if not isinstance(location, str) or not location:
        raise RuntimeError(f"Keycloak fixture response is missing a Location header for the test {fixture_kind}.")
    identifier = location.rsplit("/", 1)[-1]
    if not identifier:
        raise RuntimeError(f"Keycloak fixture response is missing an identifier for the test {fixture_kind}.")
    return identifier


def seed_keycloak(port, password):
    token = keycloak_request(
        port,
        "/realms/master/protocol/openid-connect/token",
        form=True,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": os.environ["E2E_KEYCLOAK_ADMIN_USER"],
            "password": os.environ["E2E_KEYCLOAK_ADMIN_PASSWORD"],
        },
    )["access_token"]
    realm = "/admin/realms/platform"
    lifecycle = {
        scenario: {
            "email": f"e2e-{scenario}-preview@example.test",
            "password": "Aa9!" + secrets.token_urlsafe(24),
        }
        for scenario in ("delete", "revoke", "employee")
    }
    accounts = {email: password for email in (LOGIN_EMAIL, SYNC_EMAIL)}
    accounts.update({item["email"]: item["password"] for item in lifecycle.values()})
    subjects = {}
    for email, credential in accounts.items():
        location = keycloak_request(
            port, realm + "/users", token=token,
            data={
                "username": email, "email": email, "emailVerified": True, "enabled": True,
                "firstName": "Preview", "lastName": "Fixture",
                "credentials": [{"type": "password", "value": credential, "temporary": False}],
            },
        )
        if email != LOGIN_EMAIL:
            subjects[email] = created_identifier(location, "user")
    for item in lifecycle.values():
        item["subject"] = subjects[item["email"]]
    subject = subjects[SYNC_EMAIL]
    location = keycloak_request(
        port, realm + "/organizations", token=token,
        data={"name": "Preview Integration Tenant", "alias": "kiraci1", "enabled": True},
    )
    organization = created_identifier(location, "organization")
    for member in (subject, lifecycle["delete"]["subject"], lifecycle["revoke"]["subject"]):
        keycloak_request(
            port, realm + "/organizations/" + quote(organization, safe="") + "/members",
            token=token, data=member,
        )
    return subject, lifecycle


def seed_site(project, service, bench, environment):
    source = Path(__file__).with_name("site-seed.py")
    command = ["docker", "--context", "colima", "exec", "-i", "--workdir", bench]
    for name in environment:
        command.extend(("--env", name))
    command.extend((f"{project}-{service}-1", "env/bin/python", "-", service))
    completed = subprocess.run(
        command, input=source.read_text(), text=True, stdout=subprocess.PIPE,
        env={**os.environ, **environment}, check=True,
    )
    return json.loads(completed.stdout.splitlines()[-1])


def main():
    project = os.environ["PREVIEW_PROJECT"]
    if not re.fullmatch(r"fs-e2e-preview-[a-z0-9-]+", project):
        raise SystemExit("Refusing to seed a project outside the merge preview.")
    port = int(os.environ["PANE_PORT"])
    if not 1000 <= port <= 65526:
        raise SystemExit("PANE_PORT is out of range.")
    address = ipaddress.ip_address(os.environ["E2E_PROVIDER_IP"])
    if (
        not address.is_private
        or address.is_unspecified
        or address.is_multicast
        or address.is_link_local
        or address.is_loopback
    ):
        raise SystemExit("The fake provider must use a private address on the preview network.")

    check_tenant_clients(port)
    print("Tenant browser and service client checks passed.", flush=True)
    password = "Aa9!" + secrets.token_urlsafe(24)
    subject, lifecycle = seed_keycloak(port, password)
    common = {
        "PANE_PORT": str(port), "E2E_PREVIEW_LOGIN_EMAIL": LOGIN_EMAIL,
        "E2E_LIFECYCLE_IDENTITIES": json.dumps({
            key: {field: item[field] for field in ("email", "subject")}
            for key, item in lifecycle.items()
        }),
    }
    keycloak_settings = Path(os.environ["PREVIEW_DIR"]) / "keycloak.env"
    press_service_secret = next(
        (line.partition("=")[2] for line in keycloak_settings.read_text().splitlines()
         if line.startswith("ATONOTA_PRESS_SERVICE_SECRET=")), "",
    )
    if not press_service_secret:
        raise RuntimeError("The preview Keycloak settings are missing the Press service secret.")
    press_fixture = seed_site(project, "web", PRESS_BENCH, {
        **common, "E2E_PRESS_CLIENT_SECRET": os.environ["E2E_PRESS_CLIENT_SECRET"],
        "E2E_PRESS_SERVICE_SECRET": press_service_secret,
        "E2E_PREVIEW_SYNC_ORIGIN": os.environ["IDENTITY_SYNC_EVENTS_URL"].rsplit("/v1/events", 1)[0],
    })
    fixture = seed_site(project, "kiraci-web", BENCH, {
        **common,
        "E2E_PROVIDER_IP": str(address),
        "PYTHONPATH": "/tmp",
        "E2E_KEYCLOAK_CLIENT_SECRET": os.environ["E2E_KEYCLOAK_CLIENT_SECRET"],
        "E2E_KEYCLOAK_SERVICE_CLIENT_SECRET": os.environ["E2E_KEYCLOAK_SERVICE_CLIENT_SECRET"],
    })
    fixture.update(press_fixture)
    fixture.update(
        E2E_DELETE_EMAIL=lifecycle["delete"]["email"],
        E2E_DELETE_PASSWORD=lifecycle["delete"]["password"],
        E2E_DELETE_SUBJECT=lifecycle["delete"]["subject"],
        E2E_REVOKE_SUBJECT=lifecycle["revoke"]["subject"],
        E2E_REVOKE_EMAIL=lifecycle["revoke"]["email"],
        E2E_REVOKE_PASSWORD=lifecycle["revoke"]["password"],
        E2E_MOBILE_CLIENT_ID="mobile-app",
        E2E_EMPLOYEE_EMAIL=lifecycle["employee"]["email"],
        E2E_EMPLOYEE_PASSWORD=lifecycle["employee"]["password"],
        E2E_KEYCLOAK_PASSWORD=password,
        E2E_SYNC_EMAIL=SYNC_EMAIL,
        E2E_SYNC_SUBJECT=subject,
    )
    path = Path(os.environ["PREVIEW_DIR"]) / "fixtures.json"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(fixture, stream)


if __name__ == "__main__":
    main()
