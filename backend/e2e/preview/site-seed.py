"""Run within one preview bench, with source and secrets passed on separate channels."""

import json
import os
import sys
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
        "Access Rule", title="Preview reader sees own request", document_type=doctype,
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
    provider = insert("AI Provider", provider_name="Preview Local", adapter="ollama")
    account = insert("AI Account", provider=provider, account_name="Preview Local", currency="USD")
    model = insert(
        "AI Model", provider=provider, model_id="e2e-local", context_size=4096, output_tokens_per_second=100,
    )
    api_names = [
        insert("AI API", account=account, api_name=part, base_url=provider_urls[part], priority=priority)
        for priority, part in enumerate(("limited", "fallback"))
    ]
    route = insert(
        "AI Route", route_name="e2e-local-only",
        targets=[{"api": name, "model": model} for name in api_names],
    )
    return {
        **access_fixture, "E2E_MODEL_ROUTE": route, "E2E_FALLBACK_API": api_names[1],
    }


def main():
    port = int(os.environ["PANE_PORT"])
    tenant = sys.argv[1] == "kiraci-web"
    site = "kiraci1.localhost" if tenant else "press.localhost"
    config_file = Path("sites") / site / "site_config.json"
    config = json.loads(config_file.read_text())
    config.update(
        keycloak_public_url=f"http://kimlik.localhost:{port}",
        keycloak_internal_url=f"http://kimlik.localhost:{port}",
        platform_panel_url=f"http://kiraci1.localhost:{port + 1}/panel",
    )
    service_email = "e2e-service@example.test"
    provider_urls = {}
    if tenant:
        provider_urls = {
            part: f"http://e2e-provider:{port + 7}/{part}" for part in ("limited", "fallback")
        }
        config.update(
            keycloak_client_id="site-kiraci1",
            keycloak_client_secret=os.environ["E2E_KEYCLOAK_CLIENT_SECRET"],
            kimlik_marka_adi="Atonota",
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
        )
    config_file.write_text(json.dumps(config))
    os.chdir("sites")
    frappe.init(site=site, sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    if tenant:
        fixture = seed_tenant(provider_urls)
    else:
        ensure_website_user(service_email)
        fixture = {}
    frappe.db.commit()
    print(json.dumps(fixture))


if __name__ == "__main__":
    main()
