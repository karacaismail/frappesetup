"""Public functions of the mobile module for other platform_core modules."""

from .sessions import revoke_after_commit, valid_keycloak_id
from .store import MobileStore


def close_keycloak_session(sid, subject=None):
	"""Keycloak ended this phone session (back-channel logout, G-163).

	The session is denied at once, so the phone does not keep its access token until it expires.
	Every installation bound to the session is revoked. Keycloak already ended the session, so no
	closure is sent back to Keycloak. Returns the number of installations that were revoked now.
	"""
	if not valid_keycloak_id(sid):
		return 0
	count = MobileStore().revoke_session_installations(sid)
	# A session without an installation is denied too.
	revoke_after_commit(((sid, subject),), remote=False)
	return count
