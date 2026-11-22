from functools import lru_cache
from urllib.parse import urlsplit

import frappe
from frappe import _
from werkzeug.exceptions import ServiceUnavailable


def reject():
	frappe.throw(_("Keycloak identity was rejected.", context="press_tr"), frappe.PermissionError)


def client_id():
	value = frappe.conf.keycloak_client_id
	if not value:
		raise ServiceUnavailable(_("Set the Keycloak client ID for this site.", context="press_tr"))
	return value


def issuer():
	public = frappe.conf.keycloak_public_url
	realm = frappe.conf.keycloak_realm
	if not public or not realm:
		raise ServiceUnavailable(_("Set the Keycloak URL and realm for this site.", context="press_tr"))
	return f"{public.rstrip('/')}/realms/{realm}"


def server_endpoint(endpoint):
	configured_issuer = issuer()
	public = frappe.conf.keycloak_public_url.rstrip("/")
	internal = (frappe.conf.keycloak_internal_url or public).rstrip("/")
	return configured_issuer.replace(public, internal, 1) + f"/protocol/openid-connect/{endpoint}"


def callback_url():
	origin = frappe.conf.host_name
	if not origin or urlsplit(origin).scheme not in {"https", "http"}:
		raise ServiceUnavailable(
			_("Set the Press site address before enabling Keycloak.", context="press_tr")
		)
	return origin.rstrip("/") + "/api/method/press_tr.api.auth.keycloak_callback"


@lru_cache(maxsize=32)
def jwks_cache(url):
	from oidc_verify import JwksCache

	return JwksCache(url, ttl_seconds=600)


def verify(verifier, token, **options):
	from oidc_verify import JwksUnavailable, TokenError

	try:
		return verifier(
			token,
			cache=jwks_cache(server_endpoint("certs")),
			issuer=issuer(),
			leeway=30,
			**options,
		)
	except JwksUnavailable:
		raise ServiceUnavailable(_("Keycloak keys are temporarily unavailable.", context="press_tr"))
	except TokenError:
		reject()


def claim(claims, name):
	value = claims.get(name)
	if not isinstance(value, str) or not value or len(value) > 255:
		reject()
	return value
