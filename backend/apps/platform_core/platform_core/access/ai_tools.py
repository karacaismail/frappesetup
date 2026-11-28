"""AI tools of the access rule engine, declared through the `ai_tools` hook (D-9).

The declaration format is the `x-ai-tools-hook` section of
`contracts/platform_core-yapay-zeka.openapi.yaml`. The AI layer calls `preview` and `handler`
as the user, with the validated arguments as keyword arguments. A write tool only runs after a
human approved its preview, and the layer compares `target_version` before it runs.

The tools accept structured fields only. There is no argument that carries SQL or any other
text the engine would run. The filter rows go through the same validation as a rule saved by
hand (`rules.validate_filters`).
"""

import hashlib
import json
from typing import Literal

import frappe
from frappe import _
from pydantic import BaseModel, ConfigDict, Field

from platform_core.access import explain, rules

PATH = "platform_core.access.ai_tools."
ADMIN_ROLE = "System Manager"
RULE = rules.RULE_DOCTYPE
FLAGS = tuple(f"allow_{operation}" for operation in rules.OPERATIONS)
LIST_LIMIT = 200
# Document types the generic AI write tools may not touch (O-28). They change only through the
# tools declared below, which validate a rule and warn about roles that lose access.
WRITE_CLOSED_DOCTYPES = (RULE,)

Scope = Literal["own", "team", "department", "company", "all"]
Operator = Literal["=", "!=", "in", "not in"]
Operation = Literal["read", "write", "create", "delete", "submit", "cancel"]
Scalar = str | int | float


class Strict(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")


class RuleFilter(Strict):
	field: str = Field(description="Field of the document type. It must be a real column.")
	operator: Operator = Field(description="Comparison: =, !=, in or not in.")
	value: Scalar | list[Scalar] = Field(
		description="Constant, a list of constants for in and not in, or one of $user, "
		"$user.employee, $user.department, $user.company."
	)


class ListRulesArguments(Strict):
	document_type: str | None = Field(default=None, description="Only rules of this document type.")
	role: str | None = Field(default=None, description="Only rules of this role.")
	include_inactive: bool = Field(default=False, description="Also list rules that are switched off.")


class ExplainArguments(Strict):
	doctype: str = Field(description="Document type of the record.")
	name: str = Field(description="Name of the record.")
	ptype: Operation = Field(default="read", description="Operation to explain.")
	user: str | None = Field(
		default=None,
		description="User to explain. Leave empty for the current user. Only an administrator may name another user.",
	)


class ProposeRuleArguments(Strict):
	title: str = Field(max_length=140, description="Short name of the rule.")
	document_type: str = Field(description="Document type whose records the rule narrows.")
	role: str = Field(description="Role the rule applies to.")
	scope: Scope = Field(
		description="Records the rule selects relative to the user: own, team (the user and their "
		"reports), department (with sub-departments), company or all."
	)
	match_field: str | None = Field(
		default=None,
		description="Field that ties a record to a user, employee, department or company, for example "
		"employee or owner. Required unless the scope is all.",
	)
	filters: list[RuleFilter] = Field(
		default_factory=list, description="Extra conditions. Every one of them must hold."
	)
	allow_read: bool = Field(default=False, description="The rule covers reading and listing.")
	allow_write: bool = Field(default=False, description="The rule covers changing a saved record.")
	allow_create: bool = Field(default=False, description="The rule covers creating a record.")
	allow_delete: bool = Field(default=False, description="The rule covers deleting a record.")
	allow_submit: bool = Field(default=False, description="The rule covers submitting a record.")
	allow_cancel: bool = Field(default=False, description="The rule covers cancelling a record.")
	priority: int = Field(default=0, description="Order in explanations. It never changes a decision.")
	description: str | None = Field(default=None, description="Why the rule exists.")


class ProposeRuleChangeArguments(Strict):
	name: str = Field(description="Name of the Access Rule to change, for example AR-00012.")
	is_active: bool | None = Field(default=None, description="Switch the rule on or off.")
	title: str | None = Field(default=None, max_length=140, description="New short name.")
	role: str | None = Field(default=None, description="New role.")
	scope: Scope | None = Field(default=None, description="New scope.")
	match_field: str | None = Field(default=None, description="New match field.")
	filters: list[RuleFilter] | None = Field(
		default=None, description="New conditions. They replace the old ones. An empty list removes them."
	)
	allow_read: bool | None = Field(default=None, description="Cover reading and listing.")
	allow_write: bool | None = Field(default=None, description="Cover changing a saved record.")
	allow_create: bool | None = Field(default=None, description="Cover creating a record.")
	allow_delete: bool | None = Field(default=None, description="Cover deleting a record.")
	allow_submit: bool | None = Field(default=None, description="Cover submitting a record.")
	allow_cancel: bool | None = Field(default=None, description="Cover cancelling a record.")
	priority: int | None = Field(default=None, description="New order in explanations.")
	description: str | None = Field(default=None, description="New reason for the rule.")


# --- read tools ---


def list_rules(
	document_type: str | None = None, role: str | None = None, include_inactive: bool = False
) -> dict:
	"""List Access Rules the user may read."""
	if not frappe.has_permission(RULE, "read"):
		frappe.throw(_("No permission to read Access Rules."), frappe.PermissionError)
	filters = {}
	if document_type:
		filters["document_type"] = document_type
	if role:
		filters["role"] = role
	if not include_inactive:
		filters["is_active"] = 1
	rows = frappe.get_list(
		RULE,
		filters=filters,
		fields=["name", "is_active", "description", *rules.RULE_FIELDS[1:]],
		order_by="priority asc, name asc",
		limit_page_length=LIST_LIMIT,
	)
	return {"rules": [_describe(row) for row in rows]}


def _describe(row) -> dict:
	return {
		"name": row.name,
		"title": row.title,
		"is_active": bool(row.is_active),
		"document_type": row.document_type,
		"role": row.role,
		"scope": row.scope,
		"match_field": row.match_field or None,
		"filters": [
			{"field": fieldname, "operator": operator, "value": value}
			for fieldname, operator, value in rules.parse_filters(row.filters)
		],
		"operations": [operation for operation in rules.OPERATIONS if row.get(f"allow_{operation}")],
		"priority": row.priority,
		"description": row.description or None,
	}


def explain_access(doctype: str, name: str, ptype: str = "read", user: str | None = None) -> dict:
	"""Explain why a user may or may not do something with a record."""
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("No permission to read {0}.").format(doctype), frappe.PermissionError)
	return explain.explain(doctype, name, ptype, user)


# --- write tools ---


def _doc_values(arguments: dict) -> dict:
	"""Turn tool arguments into Access Rule field values. Arguments left as None are skipped."""
	values = {}
	for key, value in arguments.items():
		if value is None or key == "name":
			continue
		if key == "filters":
			rows = [[row["field"], row["operator"], row["value"]] for row in value]
			values[key] = json.dumps(rows, ensure_ascii=False) if rows else ""
		elif isinstance(value, bool):
			values[key] = int(value)
		else:
			values[key] = value
	return values


def _require_links(doc) -> None:
	"""A preview does not save, so Frappe's own link check has not run yet."""
	if not frappe.db.exists("DocType", doc.document_type):
		frappe.throw(_("Document type {0} not found.").format(doc.document_type))
	if not frappe.db.exists("Role", doc.role):
		frappe.throw(_("Role {0} not found.").format(doc.role))


def _rule_set_version(document_type: str) -> str:
	"""Changes whenever any rule of the document type is added, changed or removed."""
	# Version stamp only. The rows are not returned (exception to G-3).
	# list-limit: the stamp needs every rule of the type, and the rule table is small.
	rows = frappe.get_all(
		RULE,
		filters={"document_type": document_type},
		fields=["name", "modified"],
		order_by="name asc",
		limit=0,  # every rule of the type; the rule table is small
	)
	stamp = "|".join(f"{row.name}:{row.modified}" for row in rows)
	return hashlib.sha256(stamp.encode()).hexdigest()


def _new_rule(arguments: dict):
	if not frappe.has_permission(RULE, "create"):
		frappe.throw(_("No permission to create Access Rules."), frappe.PermissionError)
	doc = frappe.new_doc(RULE)
	doc.update({"is_active": 1, **_doc_values(arguments)})
	_require_links(doc)
	doc.validate()
	return doc


def preview_rule(**arguments) -> dict:
	"""Describe the rule that would be created. Nothing is saved."""
	doc = _new_rule(arguments)
	first = not rules.is_governed(doc.document_type)
	operations = ", ".join(operation for operation in rules.OPERATIONS if doc.get(f"allow_{operation}"))
	return {
		"summary": _("Create an Access Rule on {0} for role {1}: scope {2}, operations {3}.").format(
			doc.document_type, doc.role, doc.scope, operations
		),
		"target_doctype": RULE,
		"target_version": _rule_set_version(doc.document_type),
		"changes": [
			{"fieldname": fieldname, "old": None, "new": doc.get(fieldname)}
			for fieldname in ("title", "document_type", "role", "scope", "match_field", "filters", *FLAGS)
			if doc.get(fieldname)
		],
		"details": {
			"first_rule_on_document_type": first,
			"roles_without_access": doc.roles_without_rule(),
			"note": _(
				"Roles listed in roles_without_access can no longer read this document type once the rule is active."
			),
		},
	}


def create_rule(**arguments) -> dict:
	"""Create the rule. The AI layer calls this only after a human approved the preview."""
	doc = _new_rule(arguments)
	doc.insert()
	return {"name": doc.name}


def _changed_rule(arguments: dict):
	"""Load the rule, apply the arguments and validate. Return the document and the changes."""
	doc = frappe.get_doc(RULE, arguments["name"])
	doc.check_permission("write")
	changes = []
	for fieldname, new in _doc_values(arguments).items():
		old = doc.get(fieldname)
		if (old or None) != (new or None) and str(old) != str(new):
			changes.append({"fieldname": fieldname, "old": old, "new": new})
	if not changes:
		frappe.throw(_("The proposal does not change the rule."))
	doc.update({change["fieldname"]: change["new"] for change in changes})
	_require_links(doc)
	doc.validate()
	return doc, changes


def preview_rule_change(**arguments) -> dict:
	"""Describe the change to a saved rule. Nothing is saved."""
	# Version stamp only. `_changed_rule` checks the write permission before anything is returned.
	version = frappe.db.get_value(RULE, arguments["name"], "modified")
	doc, changes = _changed_rule(arguments)
	fields = ", ".join(change["fieldname"] for change in changes)
	return {
		"summary": _("Change Access Rule {0} ({1}) on {2}: {3}.").format(
			doc.name, doc.title, doc.document_type, fields
		),
		"target_doctype": RULE,
		"target_name": doc.name,
		"target_version": str(version),
		"changes": changes,
		"details": {
			"roles_without_access": doc.roles_without_rule(),
			"note": _(
				"Roles listed in roles_without_access can no longer read this document type once the change is saved."
			),
		},
	}


def change_rule(**arguments) -> dict:
	"""Save the change. The AI layer calls this only after a human approved the preview."""
	doc, _changes = _changed_rule(arguments)
	doc.save()
	return {"name": doc.name}


def declare() -> list[dict]:
	"""Declarations for the `ai_tools` hook."""
	pending = " This only opens a proposal. A human must approve it before anything changes."
	return [
		{
			"name": "list_access_rules",
			"description": "List the Access Rules that narrow which records each role may use.",
			"arguments": PATH + "ListRulesArguments",
			"kind": "read",
			"roles": [ADMIN_ROLE],
			"handler": PATH + "list_rules",
		},
		{
			"name": "explain_access",
			"description": "Explain why a user may or may not read or change one record. "
			"Details about rules are returned to administrators only.",
			"arguments": PATH + "ExplainArguments",
			"kind": "read",
			"handler": PATH + "explain_access",
		},
		{
			"name": "propose_access_rule",
			"description": "Propose a new Access Rule from structured fields. The first rule on a "
			"document type removes access for every role without a rule." + pending,
			"arguments": PATH + "ProposeRuleArguments",
			"kind": "write",
			"roles": [ADMIN_ROLE],
			"destructive": True,
			"handler": PATH + "create_rule",
			"preview": PATH + "preview_rule",
		},
		{
			"name": "propose_access_rule_change",
			"description": "Propose a change to a saved Access Rule, including switching it off. "
			"Narrowing a rule removes access." + pending,
			"arguments": PATH + "ProposeRuleChangeArguments",
			"kind": "write",
			"roles": [ADMIN_ROLE],
			"destructive": True,
			"versioned": True,
			"handler": PATH + "change_rule",
			"preview": PATH + "preview_rule_change",
		},
	]
