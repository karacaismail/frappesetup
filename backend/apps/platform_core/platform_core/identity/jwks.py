"""`oidc_verify` key cache: one cache per JWKS address and process (contract section 3: 10 minutes)."""

import threading

import frappe

TTL_SECONDS = 600
_CACHES: dict = {}
_LOCK = threading.Lock()


def is_keys_unavailable(error: BaseException) -> bool:
	"""True for oidc_verify's JwksUnavailable (keys could not be fetched and none are cached).

	`oidc_verify` now exports the class (mcp_tokens.py imports it). The match by name is kept so the
	callers do not change; it accepts the same exception.
	"""
	return type(error).__name__ == "JwksUnavailable"


def report_keys_unavailable(jwks_url: str) -> None:
	"""Error Log entry without request data: only the JWKS address is recorded."""
	frappe.log_error(
		title="Identity provider keys unavailable", message=f"JWKS could not be fetched: {jwks_url}"
	)


def jwks_cache(jwks_url: str):
	from oidc_verify import JwksCache

	with _LOCK:
		cache = _CACHES.get(jwks_url)
		if cache is None:
			cache = JwksCache(jwks_url, ttl_seconds=TTL_SECONDS)
			_CACHES[jwks_url] = cache
		return cache
