"""G-138 field help on the site. The rules are in `help_content`; this module reads Frappe.

Contract: `backend/contracts/platform_core-help.openapi.yaml`.
"""

import frappe
from frappe.model import NO_VALUE_FIELDS

from platform_core.shell.help_content import (
	COMPONENT,
	FIELD,
	HELP_URL_FIELDS,
	PUBLISHED,
	coverage_report,
	resolve_component_help,
	resolve_field_help,
)
from platform_core.shell.metadata import get_doctype

TOPIC = "PLT Help Topic"
TOPIC_ROLE = "PLT Help Topic Role"
TOPIC_FIELDS = [
	"name",
	"title",
	"content",
	"layer",
	"status",
	"target_type",
	"document_type",
	"fieldname",
	"component_id",
	"app",
	"language",
	"version",
	"modified",
	*HELP_URL_FIELDS,
]
MAX_NAME = 140


def _invalid() -> None:
	frappe.throw(frappe._("A valid field is required.", context="shell.help"), frappe.ValidationError)


def _app_version(app: str) -> str | None:
	try:
		return str(frappe.get_attr(f"{app}.__version__"))
	except (AttributeError, ImportError):
		return None


def _published_topics(doctypes: list[str], fieldname: str | None = None) -> list[dict]:
	"""Read published field topics on the server. Users see them only through the field check."""
	filters = {"status": PUBLISHED, "target_type": FIELD, "document_type": ["in", doctypes]}
	if fieldname:
		filters["fieldname"] = fieldname
	return _topics_with_roles(filters)


def _topics_with_roles(filters: dict) -> list[dict]:
	"""System read of current-site topics; resolvers enforce publication, target and user roles.

	Help records are manager-editable. They are not directly readable by panel users.
	The field entry point additionally checks the shell's DocType and field permissions.
	"""
	topics = frappe.get_all(TOPIC, filters=filters, fields=TOPIC_FIELDS, order_by="modified desc")
	if not topics:
		return []
	roles: dict[str, list[str]] = {}
	for row in frappe.get_all(
		TOPIC_ROLE,
		filters={"parenttype": TOPIC, "parent": ["in", [topic.name for topic in topics]]},
		fields=["parent", "role"],
	):
		roles.setdefault(row.parent, []).append(row.role)
	return [{**topic, "roles": roles.get(topic.name, [])} for topic in topics]


def get_field_help(doctype: str, fieldname: str, user: str, language: str | None = None) -> dict:
	"""Return the help of one field. The field must be visible to the user in the shell metadata."""
	for value in (doctype, fieldname):
		if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME:
			_invalid()
	if language is not None and (not isinstance(language, str) or len(language) > 20):
		_invalid()
	# The shell metadata applies the DocType permission, permission levels, masks and the site policy.
	# It raises PermissionError when the user cannot read the document type.
	schema = get_doctype(doctype, user)["schema"]
	fields = {field["fieldname"]: field for field in schema["fields"]}
	readable = fieldname in fields
	name = schema["name"]
	answer = resolve_field_help(
		doctype=name,
		fieldname=fieldname,
		readable=readable,
		topics=_published_topics([name], fieldname) if readable else [],
		description=fields[fieldname].get("description") if readable else None,
		language=language or frappe.local.lang or "en",
		version=_app_version(frappe.get_doctype_app(name)),
		roles=frappe.get_roles(user),
	)
	if answer["message"]:
		answer["message"] = frappe._(answer["message"], context="shell.help")
	return {"doctype": name, "fieldname": fieldname, **answer}


def get_component_help(component_id: str, user: str, language: str | None = None) -> dict | None:
	"""Read component help on the request's site, restricted to the current user's roles."""
	if not isinstance(component_id, str) or not component_id.strip() or len(component_id) > MAX_NAME:
		frappe.throw(frappe._("A valid component identifier is required."), frappe.ValidationError)
	if language is not None and (not isinstance(language, str) or len(language) > 20):
		_invalid()
	topics = _topics_with_roles({"status": PUBLISHED, "target_type": COMPONENT, "component_id": component_id})
	installed_apps = set(frappe.get_installed_apps())
	versions = {
		app: _app_version(app) for app in {topic.get("app") for topic in topics} if app in installed_apps
	}
	return resolve_component_help(
		component_id=component_id,
		topics=topics,
		language=language or frappe.local.lang or "en",
		versions=versions,
		roles=frappe.get_roles(user),
	)


def get_help_coverage(app: str) -> dict:
	"""Share of value fields with help in the document types of one installed application."""
	frappe.only_for("System Manager")
	if not isinstance(app, str) or app not in frappe.get_installed_apps():
		frappe.throw(
			frappe._("Select an installed application.", context="shell.help"), frappe.ValidationError
		)
	doctypes = frappe.get_all(
		"DocType",
		filters={"module": ["in", frappe.get_module_list(app)], "istable": 0},
		pluck="name",
		order_by="name asc",
	)
	fields = [
		{
			"doctype": doctype,
			"fieldname": field.fieldname,
			"description": field.description,
			"is_custom": bool(field.get("is_custom_field")),
		}
		for doctype in doctypes
		for field in frappe.get_meta(doctype).fields
		if field.fieldtype not in NO_VALUE_FIELDS
	]
	topics = _published_topics(doctypes) if doctypes else []
	return {"app": app, **coverage_report(fields, topics)}
