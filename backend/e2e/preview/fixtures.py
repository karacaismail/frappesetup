"""Create synthetic fixture data in a merge preview's fresh, isolated sites."""

import base64
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlencode

if __package__:
    from . import browser_keycloak
else:
    import browser_keycloak

LOGIN_EMAIL = "e2e-user@example.test"
SYNC_CLIENT = "e2e-sync-fixture"
SYNC_ROLES = ("view-users", "query-users", "manage-users", "view-organizations", "manage-organizations")
BENCH = "/home/frappe/frappe-bench"
PRESS_BENCH = "/home/frappe/benches/frappe-bench"
DOCKER_PATH = shutil.which("docker")


def keycloak_request(port, path, *, token=None, data=None, form=False, expect_denial=False, method=None):
    headers = {"Host": f"identity.localhost:{port}"}
    body = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        body = urlencode(data) if form else json.dumps(data)
    method = method or ("POST" if data is not None else "GET")
    if os.environ.get("E2E_BROWSER_RUNTIME") == "container":
        status, location, raw = container_keycloak_request(port, method, path, body, headers)
    else:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            status, location, raw = response.status, response.getheader("Location"), response.read()
        finally:
            connection.close()
    if expect_denial and status in (400, 401):
        return json.loads(raw)
    if not 200 <= status < 300:
        # Do not print HTTP headers or bodies. They can contain tokens.
        raise RuntimeError(f"Keycloak fixture request returned HTTP {status} on {path}")
    return json.loads(raw) if raw else location


def docker_context():
    profile = os.environ.get("FS_COLIMA_PROFILE", "default")
    return {"default": "colima", "factory": "colima-factory"}[profile]


def docker_executable():
    if not DOCKER_PATH or not Path(DOCKER_PATH).is_absolute():
        raise RuntimeError("An absolute Docker executable path is required. Check PATH.")
    return DOCKER_PATH


def container_keycloak_request(port, method, path, body, headers):
    project = os.environ["PREVIEW_PROJECT"]
    script = """
import http.client
import json
import sys

request = json.load(sys.stdin)
connection = http.client.HTTPConnection("keycloak", request["port"], timeout=10)
try:
    connection.request(request["method"], request["path"], body=request["body"], headers=request["headers"])
    response = connection.getresponse()
    print(json.dumps([response.status, response.getheader("Location"), response.read().decode("utf-8")]))
finally:
    connection.close()
"""
    result = subprocess.run(
        [docker_executable(), "--context", docker_context(), "exec", "-i", f"{project}-tenant-web-1",
         "env/bin/python", "-c", script],
        input=json.dumps(dict(port=port, method=method, path=path, body=body, headers=headers)),
        text=True, stdout=subprocess.PIPE, check=True, timeout=20,
    )
    return json.loads(result.stdout)


def check_tenant_clients(port):
    """Exercise the disposable realm without retaining or logging its tokens."""
    path = "/realms/platform/protocol/openid-connect/token"
    browser_secret = os.environ["E2E_KEYCLOAK_CLIENT_SECRET"]
    service_secret = os.environ["E2E_KEYCLOAK_SERVICE_CLIENT_SECRET"]
    if not browser_secret or not service_secret or browser_secret == service_secret:
        raise RuntimeError("The preview requires two distinct tenant client secrets.")

    browser = {
        "grant_type": "client_credentials", "client_id": "site-tenant1",
        "client_secret": browser_secret,
    }
    for scope in ({}, {"scope": "aud-identity-sync"}):
        response = keycloak_request(port, path, data={**browser, **scope}, form=True, expect_denial=True)
        if not isinstance(response, dict) or response.get("error") not in {"unauthorized_client", "invalid_scope"}:
            raise RuntimeError("The tenant browser client did not refuse the service token request as expected.")

    service_client = "site-tenant1-service"
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


def admin_access_token(port):
    return keycloak_request(
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


def configure_sync_fixture_client(port, token=None):
    realm = "/admin/realms/platform"
    bearer = token or admin_access_token(port)

    def call(path, **kwargs):
        return keycloak_request(port, realm + path, token=bearer, **kwargs)

    generated = secrets.token_urlsafe(32)
    call("/clients", data={
        "clientId": SYNC_CLIENT, "protocol": "openid-connect", "enabled": True,
        "publicClient": False, "secret": generated, "serviceAccountsEnabled": True,
        "standardFlowEnabled": False, "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
        "defaultClientScopes": ["roles"],
    })
    scopes = {scope["name"]: scope for scope in call("/client-scopes")}
    client, = call(f"/clients?clientId={SYNC_CLIENT}")
    for scope in ("basic", "service_account", "admin-api", "kc-admin-api"):
        call(f"/clients/{client['id']}/default-client-scopes/{scopes[scope]['id']}", method="PUT", data={})
    management, = call("/clients?clientId=realm-management")
    service_user = call(f"/clients/{client['id']}/service-account-user")
    roles = [call(f"/clients/{management['id']}/roles/{name}") for name in SYNC_ROLES]
    call(f"/users/{service_user['id']}/role-mappings/clients/{management['id']}", data=roles)
    return {"client_id": SYNC_CLIENT, "client_value": generated}


def seed_keycloak(port, password, *, browser_fixtures=None):
    token = admin_access_token(port)
    realm = "/admin/realms/platform"
    lifecycle = {
        scenario: {
            "email": f"e2e-{scenario}-preview@example.test",
            "password": "Aa9!" + secrets.token_urlsafe(24),
        }
        for scenario in ("delete", "revoke", "employee")
    }
    if browser_fixtures is not None:
        lifecycle = browser_keycloak.browser_accounts()
        def call(path, **kwargs):
            return keycloak_request(port, realm + path, token=token, **kwargs)

        redirect = f"http://127.0.0.1:{port + 8}/callback"
        reader, secret = browser_keycloak.configure_browser_clients(call, redirect)
        browser_fixtures.update(
            E2E_MOBILE_REDIRECT_URI=redirect,
            E2E_MOBILE_AUDIENCE="site-tenant1",
            E2E_MOBILE_SCOPE=browser_keycloak.MOBILE_SCOPE,
            E2E_MOBILE_EXPIRED_CLIENT_ID=browser_keycloak.EXPIRED_CLIENT,
            E2E_SSO_PROBE_CLIENT=browser_keycloak.SSO_PROBE_CLIENT,
            E2E_MOBILE_ORIGIN=f"http://127.0.0.1:{port + 8}",
            E2E_MAGIC_TTL_SECONDS=str(browser_keycloak.MAGIC_TTL),
            E2E_LIFECYCLE_READER_CLIENT=reader,
            E2E_LIFECYCLE_READER_SECRET=secret,
        )
    otp_seeds = {item["email"]: item["otp_seed"] for item in lifecycle.values() if "otp_seed" in item}
    accounts = {LOGIN_EMAIL: password}
    accounts.update({item["email"]: item["password"] for item in lifecycle.values()})
    subjects = {}
    for email, credential in accounts.items():
        credentials = [{"type": "password", "value": credential, "temporary": False}]
        if email in otp_seeds:
            credentials.append(browser_keycloak.otp_credential(otp_seeds[email]))
        location = keycloak_request(
            port, realm + "/users", token=token,
            data={
                "username": email, "email": email, "emailVerified": True, "enabled": True,
                "firstName": "Preview", "lastName": "Fixture",
                "credentials": credentials,
            },
        )
        if email != LOGIN_EMAIL:
            subjects[email] = created_identifier(location, "user")
    for item in lifecycle.values():
        item["subject"] = subjects[item["email"]]
    location = keycloak_request(
        port, realm + "/organizations", token=token,
        data={"name": "Preview Integration Tenant", "alias": "tenant1", "enabled": True},
    )
    organization = created_identifier(location, "organization")
    members = (item["subject"] for key, item in lifecycle.items() if key.split("_")[-1] in {"delete", "revoke"})
    for member in members:
        keycloak_request(
            port, realm + "/organizations/" + quote(organization, safe="") + "/members",
            token=token, data=member,
        )
    return lifecycle


def seed_site(project, service, bench, environment):
    source = Path(__file__).with_name("site-seed.py")
    command = [docker_executable(), "--context", docker_context(), "exec", "-i", "--workdir", bench]
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

    docker_executable()
    check_tenant_clients(port)
    print("Tenant browser and service client checks passed.", flush=True)
    password = "Aa9!" + secrets.token_urlsafe(24)
    browser_fixtures = {} if os.environ.get("E2E_FULL_BROWSER_FIXTURES") == "1" else None
    lifecycle = seed_keycloak(port, password, browser_fixtures=browser_fixtures)
    sync_client = configure_sync_fixture_client(port)
    common = {
        "E2E_PREVIEW_SYNC_ORIGIN": os.environ["IDENTITY_SYNC_EVENTS_URL"].rsplit("/v1/events", 1)[0],
        "PANE_PORT": str(port), "E2E_PREVIEW_LOGIN_EMAIL": LOGIN_EMAIL,
        "E2E_FULL_BROWSER_FIXTURES": "1" if browser_fixtures is not None else "0",
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
    })
    fixture = seed_site(project, "tenant-web", BENCH, {
        **common,
        "E2E_PROVIDER_IP": str(address),
        "PYTHONPATH": os.environ["E2E_TENANT_MODULE_DIR"],
        "E2E_KEYCLOAK_CLIENT_SECRET": os.environ["E2E_KEYCLOAK_CLIENT_SECRET"],
        "E2E_KEYCLOAK_SERVICE_CLIENT_SECRET": os.environ["E2E_KEYCLOAK_SERVICE_CLIENT_SECRET"],
    })
    fixture.update(press_fixture)
    if browser_fixtures is None:
        for scenario in ("delete", "revoke", "employee"):
            for field in ("email", "password", "subject"):
                fixture[f"E2E_{scenario.upper()}_{field.upper()}"] = lifecycle[scenario][field]
    else:
        fixture.update(browser_fixtures)
        for engine in browser_keycloak.ENGINES:
            prefix = f"E2E_{engine.upper()}_"
            for scenario in ("delete", "revoke", "employee", "mobile"):
                account = lifecycle[f"{engine}_{scenario}"]
                for field in ("email", "password", "subject"):
                    fixture[prefix + scenario.upper() + "_" + field.upper()] = account[field]
            fixture[prefix + "MAGIC_EMAIL"] = lifecycle[f"{engine}_magic"]["email"]
            fixture[prefix + "MAGIC_EXPIRY_EMAIL"] = lifecycle[f"{engine}_magic-expiry"]["email"]
            otp = lifecycle[f"{engine}_magic-otp"]
            fixture[prefix + "MAGIC_OTP_EMAIL"] = otp["email"]
            fixture[prefix + "MAGIC_OTP_SEED"] = otp["otp_seed"]
    fixture.update(
        E2E_MOBILE_CLIENT_ID=browser_keycloak.MOBILE_CLIENT,
        E2E_KEYCLOAK_PASSWORD=password,
        E2E_SYNC_KEYCLOAK_CLIENT=sync_client["client_id"],
        E2E_SYNC_KEYCLOAK_SECRET=sync_client["client_value"],
    )
    path = Path(os.environ["PREVIEW_DIR"]) / "fixtures.json"
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(fixture, stream)


if __name__ == "__main__":
    main()
