app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# platform-core-kimlik: Keycloak sign-in, service tokens and the local sign-in gate (kimlik/README.md).
# Other tasks append to the same list keys; do not replace them.
before_login = ["platform_core.kimlik.login_policy.before_login"]
before_request = [
	"platform_core.kimlik.login_policy.before_request",
	"platform_core.kimlik.session_policy.before_request",
	"platform_core.kabuk.native_metadata.guard_website_rpc_before_request",
]
on_session_creation = ["platform_core.kimlik.session_policy.on_session_creation"]
# Keep a single list assignment. Credential hooks must precede the metadata guard (platform-core-kabuk).
auth_hooks = [
	"platform_core.kimlik.service_token.validate",
	"platform_core.kabuk.native_metadata.guard_native_metadata",
]
# AU-19: local sign-in functions are replaced by gated wrappers (kimlik/login_policy.py).
override_whitelisted_methods = {
	"frappe.core.doctype.user.user.reset_password": "platform_core.kimlik.login_policy.reset_password",
	"frappe.core.doctype.user.user.update_password": "platform_core.kimlik.login_policy.update_password",
	"frappe.core.doctype.user.user.sign_up": "platform_core.kimlik.login_policy.sign_up",
	"frappe.www.login.send_login_link": "platform_core.kimlik.login_policy.send_login_link",
	"frappe.www.login.login_via_key": "platform_core.kimlik.login_policy.login_via_key",
	"frappe.www.login.login_via_token": "platform_core.kimlik.login_policy.login_via_token",
	"frappe.integrations.oauth2_logins.login_via_google": "platform_core.kimlik.login_policy.login_via_google",
	"frappe.integrations.oauth2_logins.login_via_github": "platform_core.kimlik.login_policy.login_via_github",
	"frappe.integrations.oauth2_logins.login_via_facebook": "platform_core.kimlik.login_policy.login_via_facebook",
	"frappe.integrations.oauth2_logins.login_via_frappe": "platform_core.kimlik.login_policy.login_via_frappe",
	"frappe.integrations.oauth2_logins.login_via_office365": "platform_core.kimlik.login_policy.login_via_office365",
	"frappe.integrations.oauth2_logins.login_via_salesforce": "platform_core.kimlik.login_policy.login_via_salesforce",
	"frappe.integrations.oauth2_logins.login_via_fairlogin": "platform_core.kimlik.login_policy.login_via_fairlogin",
	"frappe.integrations.oauth2_logins.login_via_keycloak": "platform_core.kimlik.login_policy.login_via_keycloak",
	"frappe.integrations.oauth2_logins.custom": "platform_core.kimlik.login_policy.custom",
	"frappe.integrations.doctype.ldap_settings.ldap_settings.login": "platform_core.kimlik.login_policy.ldap_login",
}

# platform-core-kimlik: Frappe idle timeout of 1 hour (O-25, kimlik/session_policy.py).
# Mobile sync tables must exist before the sequence row is created.
after_install = ["platform_core.kimlik.session_policy.apply", "platform_core.mobil.store.seed_sequence"]
after_migrate = ["platform_core.kimlik.session_policy.apply", "platform_core.mobil.store.seed_sequence"]
# O-28: the identity link changes only through the identity endpoints, never through generic AI writes.
ai_write_closed_doctypes = [
	"Platform Identity Link",
	"Platform Identity Deletion",
	"AI API",
	"AI Account",
	"Mobile Revoked Session",
	"Mobile Installation",
	"Mobile Account State",
]
# Website User method allow list (docs/sozlesmeler.md). Identity adds only the method a portal user calls.
website_user_allowed_methods = [
	"platform_core.api.auth.logout",
	"platform_core.api.shell.get_bootstrap",
	"platform_core.api.meta.get_doctype",
	"frappe.auth.get_logged_user",
	"logout",
	"frappe.desk.search.search_link",
	"platform_core.api.mobile.v1_activity",
	"platform_core.api.mobile.v1_list_installations",
	"platform_core.api.mobile.v1_pull",
	"platform_core.api.mobile.v1_push",
	"platform_core.api.mobile.v1_register",
	"platform_core.api.mobile.v1_revoke",
	"platform_core.api.mobile.v1_revoke_installation",
	"platform_core.api.mobile_pwa.v1_activity",
	"platform_core.api.mobile_pwa.v1_list_installations",
	"platform_core.api.mobile_pwa.v1_pull",
	"platform_core.api.mobile_pwa.v1_push",
	"platform_core.api.mobile_pwa.v1_register",
	"platform_core.api.mobile_pwa.v1_revoke",
	"platform_core.api.mobile_pwa.v1_revoke_installation",
]

fixtures = [{"dt": "Role", "filters": [["name", "=", "AI Manager"]]}]


ai_tools = [
	"platform_core.model_gecidi.management_tools.declare",
	"platform_core.mobil.ai_tools.declarations",
]

# Shell permission generations. Keep other modules' hook entries alongside these.
clear_cache = ["platform_core.kabuk.cache.clear_cache"]

doc_events = {
	"User": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": [
			"platform_core.kabuk.cache.invalidate_permissions",
			"platform_core.mobil.store.delete_user_state",
		],
	},
	"Role": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Role Profile": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"User Permission": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom DocPerm": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"DocType": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Field": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Property Setter": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	# This DocType is installed with the access-rule module. Keep shell validators fresh after rule changes.
	"Access Rule": {
		"on_update": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"DocShare": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Role": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Workspace": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Workspace": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Sidebar": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Custom Sidebar": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Page": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Report": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Dashboard": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Dashboard Chart": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Number Card": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Module Onboarding": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Module Def": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"System Settings": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Domain Settings": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
	"Translation": {
		"on_change": ["platform_core.kabuk.cache.invalidate_permissions"],
		"on_trash": ["platform_core.kabuk.cache.invalidate_permissions"],
	},
}

after_request = ["platform_core.kabuk.headers.add_security_headers"]

after_build = ["platform_core.kabuk.assets.remove_panel_source_maps"]
