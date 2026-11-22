app_name = "press_tr"
app_title = "Press TR"
app_publisher = "Platform"
app_description = "Keycloak identity integration for Press"
app_email = "noreply@example.test"
app_license = "AGPL-3.0"

# Apps
# ------------------

required_apps = ["press"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "press_tr",
# 		"logo": "/assets/press_tr/logo.png",
# 		"title": "Press TR",
# 		"route": "/press_tr",
# 		"has_permission": "press_tr.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/press_tr/css/press_tr.css"
# app_include_js = "/assets/press_tr/js/press_tr.js"

# include js, css files in header of web template
# web_include_css = "/assets/press_tr/css/press_tr.css"
# web_include_js = "/assets/press_tr/js/press_tr.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "press_tr/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "press_tr/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "press_tr.utils.jinja_methods",
# 	"filters": "press_tr.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "press_tr.install.before_install"
# after_install = "press_tr.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "press_tr.uninstall.before_uninstall"
# after_uninstall = "press_tr.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "press_tr.utils.before_app_install"
# after_app_install = "press_tr.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "press_tr.utils.before_app_uninstall"
# after_app_uninstall = "press_tr.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "press_tr.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "press_tr.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "press_tr.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["press_tr.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"press_tr.tasks.all"
# 	],
# 	"daily": [
# 		"press_tr.tasks.daily"
# 	],
# 	"hourly": [
# 		"press_tr.tasks.hourly"
# 	],
# 	"weekly": [
# 		"press_tr.tasks.weekly"
# 	],
# 	"monthly": [
# 		"press_tr.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "press_tr.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "press_tr.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "press_tr.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["press_tr.utils.before_request"]
# after_request = ["press_tr.utils.after_request"]

# Job Events
# ----------
# before_job = ["press_tr.utils.before_job"]
# after_job = ["press_tr.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"press_tr.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

before_request = [
	"press_tr.ansible_bridge.activate",
	"press_tr.press_identity.request_policy.before_request",
]
before_job = ["press_tr.ansible_bridge.activate"]

auth_hooks = [
	"press_tr.press_identity.service.authorize_identity_sync",
	"press_tr.press_identity.request_policy.enforce_guest_allowlist",
]

before_login = "press_tr.press_identity.request_policy.block_native_login"
on_logout = "press_tr.press_identity.sessions.remove_mapping"
doc_events = {"User": {"on_update": "press_tr.press_identity.accounts.revoke_disabled_user_keys"}}
extend_doctype_class = {"Account Request": ["press_tr.press_identity.accounts.AccountRequestPolicy"]}

ai_write_closed_doctypes = ["PTR Identity Link", "PTR Keycloak Session"]
