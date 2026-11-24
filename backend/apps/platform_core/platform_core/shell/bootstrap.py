"""Use Frappe's native workspace/sidebar resolution for Website Users."""

from urllib.parse import urlsplit

import frappe
from frappe.desk.desktop import get_workspaces
from frappe.desk.doctype.sidebar.sidebar import SidebarContext, get_navigable_modules, resolve_sidebar
from frappe.desk.utils import is_item_allowed
from frappe.locale import get_date_format, get_first_day_of_the_week, get_time_format
from frappe.translate import get_all_languages
from frappe.utils import cint, get_system_timezone

from platform_core.shell.cache import permission_version
from platform_core.shell.serialization import digest

BOOTSTRAP_CACHE_SECONDS = 60

SIDEBAR_FIELDS = (
	"name",
	"module",
	"label",
	"app",
	"header_icon",
	"module_onboarding",
	"customized",
	"computed",
	"workspaces",
)
ITEM_FIELDS = (
	"key",
	"label",
	"link_to",
	"link_type",
	"type",
	"icon",
	"child",
	"collapsible",
	"indent",
	"keep_closed",
	"url",
	"show_arrow",
	"filters",
	"route_options",
	"tab",
	"open_in_new_tab",
	"is_default_module",
	"hidden",
	"derived",
)


def safe_url(value: str | None) -> bool:
	if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
		return False
	if "\\" in value or value != value.strip():
		return False
	try:
		url = urlsplit(value)
	except ValueError:
		return False
	if not url.scheme:
		return value.startswith("/") and not value.startswith("//")
	if url.scheme != "https" and not (url.scheme == "http" and cint(frappe.conf.developer_mode)):
		return False
	if not url.hostname or url.username is not None or url.password is not None:
		return False
	try:
		url.port
	except ValueError:
		return False
	hosts = frappe.conf.get("shell_navigation_hosts")
	return isinstance(hosts, list) and any(
		isinstance(host, str) and host.lower() == url.hostname for host in hosts
	)


def project_sidebar(source: dict) -> dict:
	data = {key: source[key] for key in SIDEBAR_FIELDS if key in source}
	items = []
	for row in source.get("items", []):
		if row.get("link_type") in {"URL", "Help"} and not safe_url(row.get("url")):
			continue
		item = {key: row[key] for key in ITEM_FIELDS if key in row}
		if item.get("url") and not safe_url(item["url"]):
			del item["url"]
		if isinstance(report := row.get("report"), dict):
			item["report"] = {key: report[key] for key in ("report_type", "ref_doctype") if key in report}
		items.append(item)
	return {**data, "items": items}


def get_bootstrap(user: str) -> dict:
	if not user or user == "Guest" or user != frappe.session.user:
		frappe.throw(
			frappe._("Log in to access this resource.", context="shell.session"), frappe.PermissionError
		)
	version = permission_version()
	language = frappe.local.lang or frappe.get_cached_value("User", user, "language") or "en"
	roles = sorted(frappe.get_roles(user))
	key = _bootstrap_cache_key(version, language, roles)
	cached = frappe.cache.get_value(key, user=user, expires=True)
	if cached is not None:
		return cached

	payload = _build_bootstrap(user, version, language, roles)
	# A concurrent permission commit can retire this generation while the build runs.
	# Store only under the generation read before the build, never under the new one.
	frappe.cache.set_value(key, payload, user=user, expires_in_sec=BOOTSTRAP_CACHE_SECONDS)
	return payload


def _bootstrap_cache_key(version: str, language: str, roles: list[str]) -> str:
	scope = digest(
		[language, roles, cint(frappe.conf.developer_mode), frappe.conf.get("shell_navigation_hosts")]
	)
	return f"platform_core:shell:bootstrap:v1:{version}:{scope}"


def _build_bootstrap(user: str, version: str, language: str, roles: list[str]) -> dict:
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
		data = project_sidebar(resolved.as_boot_entry())
		if any(item.get("type") == "Link" for item in data["items"]):
			sidebars.append({"name": shell, "data": data})

	user_doc = frappe.get_cached_doc("User", user)
	payload = {
		"user": {
			"name": user,
			"full_name": user_doc.full_name,
			"language": language,
			"roles": roles,
		},
		"installed_apps": apps,
		"formatting": {
			"time_zone": get_system_timezone(),
			"currency": frappe.get_system_settings("currency") or None,
			"number_format": frappe.get_system_settings("number_format") or "#,###.##",
			"rounding_method": frappe.get_system_settings("rounding_method") or "Banker's Rounding (legacy)",
			# Frappe 16 reads these from the Language record first, then System Settings (frappe/locale.py).
			"date_format": get_date_format(language),
			"time_format": get_time_format(language),
			"first_day_of_the_week": get_first_day_of_the_week(language),
		},
		"languages": enabled_languages(),
		"workspaces": [
			{
				"name": page["name"],
				"title": page.get("label") or frappe._(page.get("title") or page["name"]),
				"module": page.get("module"),
				"app": page.get("app"),
				"parent_page": page.get("parent_page") if page.get("parent_page") in allowed_names else None,
				"icon": page.get("icon"),
			}
			for page in pages
			if not page.get("app") or page.get("app") in apps
		],
		"sidebars": sidebars,
		"perm_version": version,
	}
	payload["meta_hash"] = digest(payload)
	return payload


def enabled_languages() -> list[dict]:
	"""Enabled Language records as code and display name, in a stable order."""
	rows = get_all_languages(with_language_name=True) or []
	return sorted(
		({"code": row["language_code"], "name": row["language_name"]} for row in rows),
		key=lambda row: row["code"],
	)


def workspace_target_allowed(page: dict, context) -> bool:
	if page.get("type") == "URL":
		return safe_url(page.get("external_link"))
	if page.get("type") == "Link":
		link_type = page.get("link_type") or ""
		if link_type in {"URL", "Help"}:
			return safe_url(page.get("external_link"))
		return bool(page.get("link_to")) and is_item_allowed(page["link_to"], link_type, context)
	return True


def compact_bootstrap(payload: dict) -> dict:
	"""Keep identity, formatting and languages without returning a broken navigation tree."""
	summary = {
		"user": {**payload["user"], "roles": []},
		"formatting": payload["formatting"],
		"languages": payload["languages"],
		"installed_apps": [],
		"workspaces": [],
		"sidebars": [],
		"perm_version": payload["perm_version"],
		"truncated": True,
	}
	return {**summary, "meta_hash": digest(summary)}
