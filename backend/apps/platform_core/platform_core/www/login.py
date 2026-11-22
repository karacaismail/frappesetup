"""Tenant `/login` page. Overrides Frappe's page: later-installed apps win (frappe/website/page_renderers/template_page.py:51).

With `kimlik_yalniz_keycloak` on the page shows only the brand button, which links to
`platform_core.api.auth.start_login`. With the gate off a plain password form against
`/api/method/login` is offered as well. The template is a full document, so Frappe does not wrap
it into its website base template (template_page.py:200) and none of Frappe's web assets load.
"""

from urllib.parse import urlencode

import frappe
from frappe import _

from platform_core.kimlik import helpers, site_settings
from platform_core.kimlik.exceptions import KeycloakSettingsMissing

no_cache = 1
START_PATH = "/api/method/platform_core.api.auth.start_login"


def get_context(context):
	redirect_to = frappe.local.request.args.get("redirect-to") if frappe.local.request else None
	if not helpers.is_safe_redirect(redirect_to):
		redirect_to = None

	settings = None
	try:
		settings = site_settings.get()
	except KeycloakSettingsMissing:
		pass

	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = redirect_to or (settings.panel_url if settings else "/")
		raise frappe.Redirect

	context.no_cache = 1
	context.lang = frappe.local.lang or "en"
	context.title = _("Sign in")
	context.redirect_to = redirect_to
	context.keycloak_only = site_settings.keycloak_only()
	context.configured = settings is not None
	context.brand_name = settings.brand_name if settings else ""
	context.start_url = START_PATH + ("?" + urlencode({"redirect_to": redirect_to}) if redirect_to else "")
	context.button_label = _("Sign in with {0}").format(context.brand_name) if settings else ""
	context.after_login = redirect_to or (settings.panel_url if settings else "/")
	context.login_endpoint = "/api/method/login"
	return context
