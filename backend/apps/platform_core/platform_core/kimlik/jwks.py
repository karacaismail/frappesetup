"""`oidc_verify` key cache: one cache per JWKS address and process (contract section 3: 10 minutes)."""

import threading

from oidc_verify import JwksCache

TTL_SECONDS = 600
_CACHES: dict[str, JwksCache] = {}
_LOCK = threading.Lock()


def jwks_cache(jwks_url: str) -> JwksCache:
	with _LOCK:
		cache = _CACHES.get(jwks_url)
		if cache is None:
			cache = JwksCache(jwks_url, ttl_seconds=TTL_SECONDS)
			_CACHES[jwks_url] = cache
		return cache
