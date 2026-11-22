"""Önizlemedeki sürüm işaretinin saklanan biçimi."""

import hashlib


def token(version: object) -> str | None:
	"""Sürüm işaretini karşılaştırılacak biçime çevirir. Uzun işaretin özeti kullanılır."""
	if version is None:
		return None
	text = str(version)
	return text if len(text) <= 64 else hashlib.sha256(text.encode()).hexdigest()
