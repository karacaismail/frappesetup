app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# platform-core-kimlik: Keycloak sign-in, service tokens and the local sign-in gate (kimlik/README.md).
# Other tasks append to the same list keys; do not replace them.
before_login = ["platform_core.kimlik.login_policy.before_login"]
before_request = ["platform_core.kimlik.login_policy.before_request"]
auth_hooks = ["platform_core.kimlik.service_token.validate"]
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
}

# platform-core-kimlik: Frappe idle timeout of 1 hour (O-25, kimlik/session_policy.py).
after_install = ["platform_core.kimlik.session_policy.apply"]
after_migrate = ["platform_core.kimlik.session_policy.apply"]
# O-28: the identity link changes only through the identity endpoints, never through generic AI writes.
ai_write_closed_doctypes = ["Platform Identity Link"]
