from functools import lru_cache
from urllib.parse import urlsplit

import frappe
from frappe import _


def reject():
	frappe.throw(_("Keycloak identity was rejected."), frappe.PermissionError)


def issuer():
	public = frappe.conf.keycloak_public_url
	realm = frappe.conf.keycloak_realm
	if not public or not realm:
		reject()
	return f"{public.rstrip('/')}/realms/{realm}"


def server_endpoint(endpoint):
	public = frappe.conf.keycloak_public_url.rstrip("/")
	internal = (frappe.conf.keycloak_internal_url or public).rstrip("/")
	return issuer().replace(public, internal, 1) + f"/protocol/openid-connect/{endpoint}"


def callback_url():
	origin = frappe.conf.host_name
	if not origin or urlsplit(origin).scheme not in {"https", "http"}:
		frappe.throw(_("Set the Press site address before enabling Keycloak."))
	return origin.rstrip("/") + "/api/method/press_tr.api.auth.keycloak_callback"


@lru_cache(maxsize=32)
def jwks_cache(url):
	from oidc_verify import JwksCache

	return JwksCache(url, ttl_seconds=600)


def verify(verifier, token, **options):
	from oidc_verify import TokenError

	try:
		return verifier(
			token,
			cache=jwks_cache(server_endpoint("certs")),
			issuer=issuer(),
			leeway=30,
			**options,
		)
	except TokenError:
		reject()


def claim(claims, name):
	value = claims.get(name)
	if not isinstance(value, str) or not value or len(value) > 255:
		reject()
	return value
