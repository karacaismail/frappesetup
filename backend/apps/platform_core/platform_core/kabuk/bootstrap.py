"""Use Frappe's native workspace/sidebar resolution for Website Users."""

from urllib.parse import urlsplit

import frappe
from frappe.desk.desktop import get_workspaces
from frappe.desk.doctype.sidebar.sidebar import SidebarContext, get_navigable_modules, resolve_sidebar
from frappe.desk.utils import is_item_allowed

from platform_core.kabuk.cache import permission_version
from platform_core.kabuk.http import conditional_response
from platform_core.kabuk.serialization import digest


def safe_url(value: str | None) -> bool:
	if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
		return False
	if "\\" in value or value != value.strip():
		return False
	try:
		url = urlsplit(value)
	except ValueError:
		return False
	if url.scheme:
		return url.scheme.lower() in {"https", "http"} and bool(url.hostname) and not url.username
	return value.startswith("/") and not value.startswith("//")


def get_bootstrap(user: str) -> dict | None:
	context = SidebarContext.for_modules(get_navigable_modules(), user)
	pages = [
		page
		for page in get_workspaces()["pages"]
		if not page.get("is_hidden")
		and (not page.get("for_user") or page.get("for_user") == user)
		and workspace_target_allowed(page, context.perm_ctx)
	]
	# The native Workspace Manager override includes hidden pages. A headless
	# navigation payload must not expose those pages or reference them elsewhere.
	allowed_names = {page["name"] for page in pages}
	context.perm_ctx.allowed_workspaces = allowed_names
	context.workspaces = {
		module: [name for name in names if name in allowed_names]
		for module, names in context.workspaces.items()
	}
	context.private_rows = {
		module: [row for row in rows if row.get("link_to") in allowed_names]
		for module, rows in context.private_rows.items()
	}
	apps = frappe.get_installed_apps()
	sidebars = []
	for shell in context.bases:
		resolved = resolve_sidebar(shell, user, context)
		if not resolved or (resolved.app and resolved.app not in apps):
			continue
		data = resolved.as_boot_entry()
		data["items"] = [
			item
			for item in data["items"]
			if item.get("link_type") not in {"URL", "Help"} or safe_url(item.get("url"))
		]
		if any(item.get("type") == "Link" for item in data["items"]):
			sidebars.append({"name": shell, "data": data})

	user_doc = frappe.get_cached_doc("User", user)
	payload = {
		"user": {
			"name": user,
			"full_name": user_doc.full_name,
			"language": frappe.local.lang or user_doc.language or "en",
			"roles": sorted(frappe.get_roles(user)),
		},
		"installed_apps": apps,
		"workspaces": [
			{
				"name": page["name"],
				"title": page.get("title") or page["name"],
				"module": page.get("module"),
				"app": page.get("app"),
				"parent_page": page.get("parent_page") if page.get("parent_page") in allowed_names else None,
				"icon": page.get("icon"),
			}
			for page in pages
			if not page.get("app") or page.get("app") in apps
		],
		"sidebars": sidebars,
		"perm_version": permission_version(),
	}
	payload["meta_hash"] = digest(payload)
	return conditional_response(payload, user, payload["perm_version"])


def workspace_target_allowed(page: dict, context) -> bool:
	if page.get("type") == "URL":
		return safe_url(page.get("external_link"))
	if page.get("type") == "Link":
		link_type = page.get("link_type") or ""
		if link_type in {"URL", "Help"}:
			return safe_url(page.get("external_link"))
		return bool(page.get("link_to")) and is_item_allowed(page["link_to"], link_type, context)
	return True
