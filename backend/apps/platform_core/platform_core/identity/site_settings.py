"""Reads site settings. Keys are listed in docs/sozlesmeler.md, section 8. Secrets stay in site config (G-9)."""

import frappe
from frappe import _
from frappe.utils import cint

from platform_core.identity import helpers
from platform_core.identity.exceptions import KeycloakSettingsMissing

REQUIRED = (
	"keycloak_public_url",
	"keycloak_client_id",
	"keycloak_client_secret",
	"identity_brand_name",
	"platform_panel_url",
)
DEFAULT_REALM = "platform"
DEFAULT_SERVICE_AZP = ("identity-sync",)


def realm() -> str:
	return frappe.conf.get("keycloak_realm") or DEFAULT_REALM


def issuer() -> str:
	"""Only the `iss` value. The login hook does not need every setting."""
	public_url = frappe.conf.get("keycloak_public_url")
	if not public_url:
		frappe.throw(
			_("Keycloak settings are missing: {0}", context="platform_core.identity").format(
				"keycloak_public_url"
			),
			KeycloakSettingsMissing,
		)
	return helpers.issuer_url(public_url, realm())


def keycloak_only() -> bool:
	return bool(cint(frappe.conf.get("identity_keycloak_only")))


def get() -> frappe._dict:
	"""All identity settings, validated."""
	conf = frappe.conf
	missing = [key for key in REQUIRED if not conf.get(key)]
	if missing:
		frappe.throw(
			_("Keycloak settings are missing: {0}", context="platform_core.identity").format(
				", ".join(missing)
			),
			KeycloakSettingsMissing,
		)
	public_url = conf.keycloak_public_url.rstrip("/")
	internal_url = (conf.get("keycloak_internal_url") or public_url).rstrip("/")
	azp = conf.get("identity_service_azp") or list(DEFAULT_SERVICE_AZP)
	if isinstance(azp, str):
		azp = [azp]
	return frappe._dict(
		public_url=public_url,
		internal_url=internal_url,
		realm=realm(),
		client_id=conf.keycloak_client_id,
		client_secret=conf.keycloak_client_secret,
		brand_name=conf.identity_brand_name,
		panel_url=conf.platform_panel_url,
		issuer=helpers.issuer_url(public_url, realm()),
		jwks_url=helpers.jwks_url(internal_url, realm()),
		service_azp=frozenset(azp),
		keycloak_only=keycloak_only(),
	)
