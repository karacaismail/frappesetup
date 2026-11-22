"""Site-local permission generations."""

from uuid import uuid4

import frappe

VERSION_KEY = "platform_core:kabuk:permission_version"


def permission_version() -> str:
	version = frappe.cache.get_value(VERSION_KEY)
	if not version:
		version = bump_permission_version()
	return version


def bump_permission_version() -> str:
	"""Opaque generations cannot collide after Redis/global-cache resets."""
	version = uuid4().hex
	frappe.cache.set_value(VERSION_KEY, version)
	return version


def invalidate_permissions(doc=None, method=None) -> None:
	"""Only committed permission changes invalidate other requests."""
	frappe.db.after_commit.add(bump_permission_version)


def clear_cache() -> None:
	"""Frappe calls the global clear_cache hook without arguments."""
	bump_permission_version()
