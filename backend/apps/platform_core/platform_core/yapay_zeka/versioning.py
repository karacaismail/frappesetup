"""The stored form of the version marker of a preview."""

import hashlib


def token(version: object) -> str | None:
	"""Turn a version marker into the form that is compared. A long marker is stored as its hash."""
	if version is None:
		return None
	text = str(version)
	return text if len(text) <= 64 else hashlib.sha256(text.encode()).hexdigest()
