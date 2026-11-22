"""`oidc_verify` key cache: one cache per JWKS address and process (contract section 3: 10 minutes)."""

import threading

from oidc_verify import JwksCache

TTL_SECONDS = 600
_CACHES: dict[str, JwksCache] = {}
_LOCK = threading.Lock()


def is_keys_unavailable(error: BaseException) -> bool:
	"""True for oidc_verify's JwksUnavailable (keys could not be fetched and none are cached).

	The package does not export that class yet, and the module boundary check forbids importing
	`oidc_verify.hatalar` directly. kimlik-realm was asked to export it; until then it is matched by name.
	"""
	return type(error).__name__ == "JwksUnavailable"


def jwks_cache(jwks_url: str) -> JwksCache:
	with _LOCK:
		cache = _CACHES.get(jwks_url)
		if cache is None:
			cache = JwksCache(jwks_url, ttl_seconds=TTL_SECONDS)
			_CACHES[jwks_url] = cache
		return cache
