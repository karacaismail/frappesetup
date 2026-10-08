app_name = "school_ext"
app_title = "School Ext"
app_publisher = "Fixture Publisher"
app_description = "Fixture app with deliberate problems"
app_email = "dev@example.test"
app_license = "mit"

required_apps = ["erpnext"]

doc_events = {
	"Sales Invoice": {
		"validate": "school_ext.events.sales_invoice.validate",
		"on_submit": "school_ext.events.missing.handler",
	},
	"*": {"on_update": "school_ext.events.audit.log"},
}

override_doctype_class = {"Student": "school_ext.overrides.student.CustomStudent"}

extend_doctype_class = {"Task": ["school_ext.overrides.task.TaskMixin"]}

fixtures = ["Custom Field", {"dt": "Property Setter", "filters": [["module", "=", "School Ext"]]}]
