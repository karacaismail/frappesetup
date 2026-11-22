"""Stand-in mobile endpoint for the tests of `platform_core.kimlik.api` (the real ones belong to platform-core-mobil).

The function is not whitelisted at import time, so `/api/method` cannot call it on a running site.
Only a test registers it, through `register()`, and removes it again (ai-readiness finding, D-9).
"""

from collections.abc import Callable

import frappe


def v1_whoami() -> dict:
	identity = getattr(frappe.local, "mobile_identity", None) or {}
	return {"user": frappe.session.user, "identity": {k: v for k, v in identity.items() if k != "scope"}}


def register() -> Callable[[], None]:
	"""Whitelists the stub for this test process only. Returns the function that removes it again."""
	if not frappe.in_test:
		raise RuntimeError("The mobile stub is only for tests.")
	import sys

	module = sys.modules[__name__]
	original = module.v1_whoami
	# `frappe.whitelist` returns a type-checking wrapper (frappe/__init__.py:462). The wrapper is the
	# whitelisted object, so the module attribute must point to it while the test runs.
	wrapped = frappe.whitelist(methods=["POST"])(original)
	module.v1_whoami = wrapped

	def unregister() -> None:
		frappe.whitelisted.discard(wrapped)
		frappe.allowed_http_methods_for_whitelisted_func.pop(wrapped, None)
		module.v1_whoami = original

	return unregister
