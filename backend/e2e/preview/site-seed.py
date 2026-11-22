"""Run within one preview bench, with source and secrets passed on separate channels."""

import json
import os
import sys
from pathlib import Path

import frappe


def insert(doctype, **fields):
    return frappe.get_doc(doctype=doctype, **fields).insert().name


def ensure_website_user(email):
    if not frappe.db.exists("User", email):
        insert("User", email=email, first_name="Preview", user_type="Website User", send_welcome_email=0)


def seed_tenant(provider_urls):
    from platform_core.erisim.tests.base import (
        DOCTYPE, EMPLOYEE_1, EMPLOYEE_2, PASSWORD, RULE_DOCTYPE, ErisimTestCase, ensure_fixtures,
    )

    ensure_website_user(os.environ["E2E_PREVIEW_LOGIN_EMAIL"])
    ensure_fixtures()
    for rule in ErisimTestCase.RULES:
        insert(RULE_DOCTYPE, document_type=DOCTYPE, is_active=1, **rule)
    visible = ErisimTestCase.insert_record(EMPLOYEE_1)
    hidden = ErisimTestCase.insert_record(EMPLOYEE_2)
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
        "E2E_DOCTYPE": DOCTYPE, "E2E_VISIBLE_RECORD": visible, "E2E_HIDDEN_RECORD": hidden,
        "E2E_MODEL_ROUTE": route, "E2E_FALLBACK_API": api_names[1], "E2E_UPDATE_FIELD": "title",
        "E2E_PREVIEW_READER_EMAIL": EMPLOYEE_1, "E2E_PREVIEW_READER_PASSWORD": PASSWORD,
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
