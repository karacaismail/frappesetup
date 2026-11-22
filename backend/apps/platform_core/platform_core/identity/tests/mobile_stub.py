"""Stand-in mobile endpoint for the tests of `platform_core.kimlik.api` (the real ones belong to platform-core-mobil).

The function is not whitelisted at import time, so `/api/method` cannot call it on a running site.
Only a test registers it, through `register()`, and removes it again (ai-readiness finding, D-9).
"""

from collections.abc import Callable

import frappe


def v1_whoami() -> dict:
	identity = getattr(frappe.local, "mobile_identity", None) or {}
	return {"user": frappe.session.user, "site": frappe.local.site, "identity": dict(identity)}


def register() -> Callable[[], None]:
	"""Whitelists the stub for this test process only. Returns the function that removes it again."""
	if not frappe.in_test:
		raise RuntimeError("The mobile stub is only for tests.")
	function = v1_whoami
	frappe.whitelisted.add(function)
	frappe.allowed_http_methods_for_whitelisted_func[function] = ["POST"]
	# Mobile calls run as the Website User. The shell's method allow list (docs/sozlesmeler.md) must
	# list the stub while the test runs, as the mobile module lists its real endpoints.
	real_get_hooks = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		value = real_get_hooks(hook, *args, **kwargs)
		if hook == "website_user_allowed_methods":
			return [*value, f"{__name__}.v1_whoami"]
		return value

	frappe.get_hooks = get_hooks

	def unregister() -> None:
		frappe.whitelisted.discard(function)
		frappe.allowed_http_methods_for_whitelisted_func.pop(function, None)
		frappe.get_hooks = real_get_hooks

	return unregister
