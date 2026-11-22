"""Prepare synthetic users and clients in the disposable preview realm."""

import base64
import json
import secrets

ENGINES = ("chromium", "webkit")
MOBILE_CLIENT = "mobile-app"
EXPIRED_CLIENT = "e2e-expired-mobile"
MOBILE_SCOPE = "openid mobile aud-site-tenant1"
SCENARIOS = ("delete", "revoke", "employee", "mobile", "magic", "magic-otp")
MAGIC_TTL = 45


def browser_accounts():
    accounts = {}
    for engine in ENGINES:
        for scenario in SCENARIOS:
            account = {
                "email": f"e2e-{scenario}-{engine}@example.test",
                "password": "Aa9!" + secrets.token_urlsafe(24),
            }
            if scenario == "magic-otp":
                account["otp_seed"] = base64.b32encode(secrets.token_urlsafe(20).encode()).decode()
            accounts[f"{engine}_{scenario}"] = account
    return accounts


def otp_credential(seed):
    return {
        "type": "otp",
        "secretData": json.dumps({"value": base64.b32decode(seed).decode()}),
        "credentialData": json.dumps({
            "subType": "totp", "digits": 6, "counter": 0, "period": 30, "algorithm": "HmacSHA1",
        }),
    }


def configure_browser_clients(call, redirect):
    scopes = {scope["name"]: scope for scope in call("/client-scopes")}
    if "mobile" not in scopes:
        call("/client-scopes", data={
            "name": "mobile", "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "false"},
        })
        scopes = {scope["name"]: scope for scope in call("/client-scopes")}

    client, = call(f"/clients?clientId={MOBILE_CLIENT}")
    client["redirectUris"] = [redirect]
    client["attributes"]["post.logout.redirect.uris"] = redirect
    call(f"/clients/{client['id']}", method="PUT", data=client)
    for scope in ("mobile", "aud-site-tenant1"):
        call(f"/clients/{client['id']}/optional-client-scopes/{scopes[scope]['id']}", method="PUT", data={})

    call("/clients", data={
        "clientId": EXPIRED_CLIENT, "protocol": "openid-connect", "enabled": True,
        "publicClient": True, "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
        "fullScopeAllowed": False, "redirectUris": [redirect],
        "attributes": {"pkce.code.challenge.method": "S256", "access.token.lifespan": "1"},
    })
    expired, = call(f"/clients?clientId={EXPIRED_CLIENT}")
    for item in (client, expired):
        defaults = call(f"/clients/{item['id']}/default-client-scopes")
        for scope in defaults:
            if scope["name"] == "roles":
                call(f"/clients/{item['id']}/default-client-scopes/{scope['id']}", method="DELETE")
    for scope in ("mobile", "aud-site-tenant1"):
        call(f"/clients/{expired['id']}/optional-client-scopes/{scopes[scope]['id']}", method="PUT", data={})

    executions = call("/authentication/flows/atonota-browser-magic-link/executions")
    config_id, = (row["authenticationConfig"] for row in executions if row.get("providerId") == "magiclink")
    config = call(f"/authentication/config/{config_id}")
    config["config"]["magickey.validity.duration"] = str(MAGIC_TTL)
    call(f"/authentication/config/{config['id']}", method="PUT", data=config)

    reader_id = "e2e-browser-reader"
    reader_secret = secrets.token_urlsafe(32)
    call("/clients", data={
        "clientId": reader_id, "protocol": "openid-connect", "enabled": True,
        "publicClient": False, "secret": reader_secret, "serviceAccountsEnabled": True,
        "standardFlowEnabled": False, "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
        "defaultClientScopes": ["roles"],
    })
    reader, = call(f"/clients?clientId={reader_id}")
    call(f"/clients/{reader['id']}/default-client-scopes/{scopes['kc-admin-api']['id']}", method="PUT", data={})
    management, = call("/clients?clientId=realm-management")
    service_user = call(f"/clients/{reader['id']}/service-account-user")
    role = call(f"/clients/{management['id']}/roles/view-users")
    call(f"/users/{service_user['id']}/role-mappings/clients/{management['id']}", data=[role])
    call(f"/clients/{reader['id']}/scope-mappings/clients/{management['id']}", data=[role])
    return reader_id, reader_secret
