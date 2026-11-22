"""Run within one preview bench, with source and secrets passed on separate channels."""

import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe

import frappe


def insert(doctype, **fields):
    return frappe.get_doc(doctype=doctype, **fields).insert().name


def ensure_website_user(email):
    if not frappe.db.exists("User", email):
        insert("User", email=email, first_name="Preview", user_type="Website User", send_welcome_email=0)


def seed_access_fixture():
    """Create the minimal two-record access scenario on the disposable tenant."""
    doctype = "Preview Access Request"
    role = "Preview Access Reader"
    reader = "e2e-access-reader@example.test"
    password = "Aa9!" + token_urlsafe(24)

    insert("Role", role_name=role, desk_access=1)
    insert(
        "DocType",
        name=doctype,
        module="Custom",
        custom=1,
        autoname="hash",
        fields=[
            {"fieldname": "title", "fieldtype": "Data", "label": "Title"},
            {"fieldname": "request_user", "fieldtype": "Link", "options": "User", "label": "Request User"},
        ],
        permissions=[{"role": role, "read": 1}, {"role": "System Manager", "read": 1, "write": 1}],
    )
    insert(
        "User", email=reader, first_name="Preview Reader", send_welcome_email=0,
        roles=[{"role": role}], new_password=password,
    )
    insert(
        "PLT Access Rule", title="Preview reader sees own request", document_type=doctype,
        role=role, scope="own", match_field="request_user", allow_read=1, is_active=1, priority=10,
    )
    return {
        "E2E_DOCTYPE": doctype,
        "E2E_VISIBLE_RECORD": insert(doctype, title="Visible request", request_user=reader),
        "E2E_HIDDEN_RECORD": insert(doctype, title="Hidden request", request_user="Administrator"),
        "E2E_UPDATE_FIELD": "title",
        "E2E_PREVIEW_READER_EMAIL": reader,
        "E2E_PREVIEW_READER_PASSWORD": password,
    }


def seed_tenant(provider_urls):
    ensure_website_user(os.environ["E2E_PREVIEW_LOGIN_EMAIL"])
    access_fixture = seed_access_fixture()
    provider = insert("PLT AI Provider", provider_name="Preview Local", adapter="ollama")
    account = insert("PLT AI Account", provider=provider, account_name="Preview Local", currency="USD")
    model = insert(
        "PLT AI Model", provider=provider, model_id="e2e-local", context_size=4096, output_tokens_per_second=100,
    )
    api_names = [
        insert("PLT AI API", account=account, api_name=part, base_url=provider_urls[part], priority=priority)
        for priority, part in enumerate(("limited", "fallback"))
    ]
    route = insert(
        "PLT AI Route", route_name="e2e-local-only",
        targets=[{"api": name, "model": model} for name in api_names],
    )
    return {
        **access_fixture, "E2E_MODEL_ROUTE": route, "E2E_FALLBACK_API": api_names[1],
    }


def deletion_accounts(identities):
    return [(f"E2E_{name.split('_')[0].upper()}_" if "_" in name else "E2E_", account)
            for name, account in identities.items() if name.split("_")[-1] == "delete"]


def seed_lifecycle_identities(identities, issuer, tenant):
    if tenant:
        from platform_core.identity.provisioning import provision

        for account in identities.values():
            provision({
                "issuer": issuer, "subject": account["subject"], "email": account["email"],
                "email_verified": True, "enabled": True, "first_name": "Preview",
            })
        return {}

    from frappe.core.doctype.user.user import generate_keys
    from press_tr.press_identity.identity import bind_identity, ensure_personal_team

    fixture = {}
    for prefix, account in deletion_accounts(identities):
        link = bind_identity({
            "iss": issuer, "sub": account["subject"], "email": account["email"], "email_verified": True,
        })
        if os.environ["E2E_FULL_BROWSER_FIXTURES"] == "1":
            ensure_personal_team(link.user)
        keys = generate_keys(account["email"])
        fixture[prefix + "DELETE_PRESS_AUTHORIZATION"] = f"token {keys['api_key']}:{keys['api_secret']}"
        fixture[prefix + "DELETE_PRESS_ANONYMOUS_USER"] = (
            f"deleted-{sha256(link.name.encode()).hexdigest()[:32]}@invalid.example"
        )
    if os.environ["E2E_FULL_BROWSER_FIXTURES"] == "1":
        from frappe.sessions import Session
        from werkzeug.wrappers import Request

        frappe.local.request = Request.from_values()
        frappe.local.request_ip = "127.0.0.1"
        session = Session("Administrator", full_name="Administrator", user_type="System User")
        fixture["E2E_DELETE_PRESS_READER_COOKIE"] = "sid=" + session.sid
    return fixture


def main():
    port = int(os.environ["PANE_PORT"])
    tenant = sys.argv[1] == "tenant-web"
    lifecycle = json.loads(os.environ["E2E_LIFECYCLE_IDENTITIES"])
    site = "tenant1.localhost" if tenant else "press.localhost"
    config_file = Path("sites") / site / "site_config.json"
    config = json.loads(config_file.read_text())
    config.update(
        keycloak_public_url=f"http://identity.localhost:{port}",
        keycloak_internal_url=f"http://identity.localhost:{port}",
        platform_panel_url=f"http://tenant1.localhost:{port + 1}/panel",
    )
    service_email = "e2e-service@example.test"
    provider_urls = {}
    if tenant:
        config.pop("keycloak_service_client_secret", None)
        if os.environ["E2E_FULL_BROWSER_FIXTURES"] == "1":
            config["allow_cors"] = [f"http://127.0.0.1:{port + 8}"]
            config["mobile_identity_sync_url"] = "https://identity-sync:9443"
            config["keycloak_internal_url"] = "https://identity-sync:9444"
        else:
            config["mobile_identity_sync_url"] = os.environ["E2E_PREVIEW_SYNC_ORIGIN"]
            config["mobile_allow_development_http"] = 1
        provider_urls = {
            part: f"http://e2e-provider:{port + 7}/{part}" for part in ("limited", "fallback")
        }
        config.update(
            keycloak_client_id="site-tenant1",
            keycloak_client_secret=os.environ["E2E_KEYCLOAK_CLIENT_SECRET"],
            keycloak_service_client_id="site-tenant1-service",
            extra_config="preview_site_config.tenant_service_config",
            identity_brand_name="Atonota",
            kimlik_mobil_azp=["mobile-app", "e2e-expired-mobile"] if
            os.environ["E2E_FULL_BROWSER_FIXTURES"] == "1" else ["mobile-app"],
            kimlik_deletion_hmac_key=token_urlsafe(32),
            mobile_cursor_key=token_urlsafe(32),
            model_gateway_endpoints={
                url: {"kind": "local", "addresses": [os.environ["E2E_PROVIDER_IP"]]}
                for url in provider_urls.values()
            },
        )
    else:
        config.update(
            host_name=f"http://press.localhost:{port + 3}",
            keycloak_realm="platform",
            keycloak_client_id="press",
            keycloak_client_secret=os.environ["E2E_PRESS_CLIENT_SECRET"],
            press_identity_sync_user=service_email,
            press_anonymization_hmac_key=token_urlsafe(32),
            identity_sync_url=os.environ["E2E_PREVIEW_SYNC_ORIGIN"],
            press_service_client_secret=os.environ["E2E_PRESS_SERVICE_SECRET"],
        )
    config_file.write_text(json.dumps(config))
    os.chdir("sites")
    frappe.init(site=site, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    if not tenant:
        ensure_website_user(service_email)
    issuer = f"http://identity.localhost:{port}/realms/platform"
    fixture = seed_lifecycle_identities(lifecycle, issuer, tenant)
    if tenant:
        from platform_core.identity.anonymization import identity_hash

        fixture.update(seed_tenant(provider_urls))
        for prefix, account in deletion_accounts(lifecycle):
            doctype = fixture["E2E_DOCTYPE"]
            digest = identity_hash(issuer, account["subject"])
            anonymous = f"deleted-user-{digest[:16]}@deleted.invalid"
            fixture.update({
                prefix + "DELETE_RECORD_DOCTYPE": doctype,
                prefix + "DELETE_RECORD_NAME": insert(
                    doctype, title="Retained lifecycle request", request_user=account["email"],
                ),
                prefix + "DELETE_RECORD_PERSON_FIELD": "request_user",
                prefix + "DELETE_RECORD_ANONYMOUS_VALUE": json.dumps(anonymous),
                prefix + "DELETE_TENANT_ANONYMOUS_USER": anonymous,
            })
    frappe.db.commit()
    print(json.dumps(fixture))


if __name__ == "__main__":
    main()
