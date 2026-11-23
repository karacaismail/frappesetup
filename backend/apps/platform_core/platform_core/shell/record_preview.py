"""A panel record card whose metadata is independent of tenant records."""

from urllib.parse import quote, urlencode

from frappe import _
from frappe.utils import get_url


def context_for(path):
	parts = path.strip("/").split("/")
	if len(parts) != 4 or parts[0] != "panel":
		return None
	if any(len(part) > 140 or not part or part in {".", ".."} or "\\" in part for part in parts):
		return None
	canonical_path = "/" + "/".join(quote(part, safe="") for part in parts)
	image_path = "/api/method/platform_core.api.shell.record_preview_image"
	return {
		"title": _("Record", context="shell.record_preview"),
		"description": _("Sign in to open this record.", context="shell.record_preview"),
		"url": get_url(canonical_path, allow_header_override=False),
		"image": get_url(image_path, allow_header_override=False),
		"login": "/login?" + urlencode({"redirect-to": canonical_path}),
	}
