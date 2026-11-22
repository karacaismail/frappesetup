"""Create synthetic fixture data in a merge preview's fresh, isolated sites."""

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


def keycloak_request(port, path, *, token=None, data=None, form=False):
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
        if not 200 <= response.status < 300:
            # Do not print HTTP headers or bodies. They can contain tokens.
            raise RuntimeError(f"Keycloak fixture request returned HTTP {response.status} on {path}")
        return json.loads(raw) if raw else response.getheader("Location")
    finally:
        connection.close()


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
    for email in (LOGIN_EMAIL, SYNC_EMAIL):
        location = keycloak_request(
            port, realm + "/users", token=token,
            data={
                "username": email, "email": email, "emailVerified": True, "enabled": True,
                "firstName": "Preview", "lastName": "Fixture",
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
        )
        if email == SYNC_EMAIL:
            subject = created_identifier(location, "user")
    location = keycloak_request(
        port, realm + "/organizations", token=token,
        data={"name": "Preview Integration Tenant", "alias": "kiraci1", "enabled": True},
    )
    organization = created_identifier(location, "organization")
    keycloak_request(
        port, realm + "/organizations/" + quote(organization, safe="") + "/members",
        token=token, data=subject,
    )
    return subject


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
    if service == "kiraci-web":
        return json.loads(completed.stdout.splitlines()[-1])
    return {}


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

    password = "Aa9!" + secrets.token_urlsafe(24)
    subject = seed_keycloak(port, password)
    common = {"PANE_PORT": str(port), "E2E_PREVIEW_LOGIN_EMAIL": LOGIN_EMAIL}
    seed_site(project, "web", PRESS_BENCH, {
        **common, "E2E_PRESS_CLIENT_SECRET": os.environ["E2E_PRESS_CLIENT_SECRET"],
    })
    fixture = seed_site(project, "kiraci-web", BENCH, {
        **common,
        "E2E_PROVIDER_IP": str(address),
        "E2E_KEYCLOAK_CLIENT_SECRET": os.environ["E2E_KEYCLOAK_CLIENT_SECRET"],
    })
    fixture.update(
        E2E_KEYCLOAK_PASSWORD=password,
        E2E_SYNC_EMAIL=SYNC_EMAIL,
        E2E_SYNC_SUBJECT=subject,
    )
    path = Path(os.environ["PREVIEW_DIR"]) / "fixtures.json"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(fixture, stream)


if __name__ == "__main__":
    main()
