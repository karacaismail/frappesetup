"""Setup step for the Keycloak “Social Login Key”. Safe to run twice (V-7).

The record keeps the client credentials in Frappe's standard place. It stays disabled: this app signs in
through its own callback (`platform_core.api.auth.keycloak_callback`), and Frappe's own button would send a
`state` this app does not know. The record name must be `keycloak`, the name Frappe's own callback
`login_via_keycloak` would use (`frappe/integrations/oauth2_logins.py:47`). The name is derived from `provider_name` only on insert
(`social_login_key.py:73`). So the record is inserted as “Keycloak” and the display name is then set
to the brand name.

Manual run: `bench --site <site> execute platform_core.kimlik.provider_setup.ensure_social_login_key`
HTTP counterpart: `platform_core.api.auth.setup_keycloak_login` (D-9).
"""

import json

import frappe

from platform_core.identity import helpers, site_settings

AUTH_URL_DATA = {"response_type": "code", "scope": "openid"}


def ensure_social_login_key() -> dict:
	settings = site_settings.get()
	if frappe.db.exists("Social Login Key", helpers.PROVIDER):
		doc = frappe.get_doc("Social Login Key", helpers.PROVIDER)
	else:
		doc = frappe.new_doc("Social Login Key")
		doc.provider_name = helpers.PROVIDER_BASE_NAME

	if doc.is_new():
		# `social_login_provider` is set_only_once as well (social_login_key.json); existing records keep theirs.
		doc.social_login_provider = helpers.PROVIDER_BASE_NAME
	doc.update(
		{
			"enable_social_login": 0,
			"custom_base_url": 1,
			"base_url": helpers.realm_url(settings.public_url, settings.realm),
			"authorize_url": "/protocol/openid-connect/auth",
			"access_token_url": "/protocol/openid-connect/token",
			"api_endpoint": "/protocol/openid-connect/userinfo",
			"api_endpoint_args": None,
			"redirect_url": helpers.CALLBACK_PATH,
			"client_id": settings.client_id,
			"client_secret": settings.client_secret,
			"user_id_property": "sub",
			"sign_ups": "Deny",
			"auth_url_data": json.dumps(AUTH_URL_DATA),
		}
	)
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	if doc.provider_name != settings.brand_name:
		# `provider_name` is set_only_once because the record name derives from it on insert
		# (social_login_key.py:73, document.py:1141). The name stays `keycloak`; only the display label
		# changes, so the value is written directly (V-1 exception, no other validation depends on it).
		frappe.db.set_value("Social Login Key", doc.name, "provider_name", settings.brand_name)
		doc.provider_name = settings.brand_name
	return {"social_login_key": doc.name, "enabled": False, "provider_name": doc.provider_name}
