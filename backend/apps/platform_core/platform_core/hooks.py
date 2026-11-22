app_name = "platform_core"
app_title = "Platform Core"
app_publisher = "Platform"
app_description = "Platform backend modules"
app_email = "noreply@example.test"
app_license = "mit"

# Access rule engine (erisim-kurali task). Decision note: docs/kararlar/0006-erisim-kurali.md
permission_query_conditions = {"*": "platform_core.erisim.hooks.query_conditions"}
has_permission = {"*": "platform_core.erisim.hooks.has_permission"}
# On a document type with Access Rules every custom link search is refused. There is no allow-list.
override_whitelisted_methods = {
	"frappe.desk.search.search_link": "platform_core.erisim.link_search.search_link",
	"frappe.desk.search.search_widget": "platform_core.erisim.link_search.search_widget",
}
# The report gate. Each extension class calls super(), so extensions of other apps keep running.
extend_doctype_class = {
	"Report": ["platform_core.erisim.reports.GuardedReport"],
	"Prepared Report": ["platform_core.erisim.reports.GuardedPreparedReport"],
	"Auto Email Report": ["platform_core.erisim.reports.GuardedAutoEmailReport"],
	"File": ["platform_core.erisim.reports.GuardedFile"],
}
doc_events = {
	"Role": {
		"after_rename": "platform_core.erisim.rules.clear_cache",
		"on_trash": "platform_core.erisim.rules.clear_cache",
	},
	"DocType": {
		"after_rename": "platform_core.erisim.rules.clear_cache",
		"on_trash": "platform_core.erisim.rules.clear_cache",
	},
}
# AI tools of the access rule engine (D-9). Format: contracts/platform_core-yapay-zeka.openapi.yaml
ai_tools = ["platform_core.erisim.ai_tools.declare"]
# Access Rules change only through the engine's own AI tools, not the generic write tools (O-28).
ai_write_closed_doctypes = ["Access Rule"]
# Auto Email Reports on governed data are switched off; existing ones are disabled here.
after_install = "platform_core.erisim.reports.switch_off_governed_auto_email_reports"
after_migrate = ["platform_core.erisim.reports.switch_off_governed_auto_email_reports"]
# A Prepared Report queued before a rule existed is refused when its job starts.
before_job = ["platform_core.erisim.reports.refuse_prepared_report_job"]
