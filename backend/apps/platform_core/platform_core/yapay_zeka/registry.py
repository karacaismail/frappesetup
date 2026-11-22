"""Tool registry: built-in tools and those that apps declare with the `ai_tools` hook (G-105)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cached_property
from typing import Any

import frappe
from frappe.mcp.tools import CompactJsonSchema, ToolArguments
from pydantic import BaseModel

from platform_core.yapay_zeka import policy

APP_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
DECLARATION_KEYS = frozenset(
	{
		"name",
		"description",
		"arguments",
		"kind",
		"roles",
		"destructive",
		"billable",
		"handler",
		"preview",
		"prepare",
		"versioned",
	}
)


@dataclass(frozen=True)
class AiTool:
	name: str
	description: str
	arguments: type[BaseModel]
	handler: Callable[..., Any]
	tool_class: str
	kind: str = "read"
	preview: Callable[..., dict] | None = None
	roles: tuple[str, ...] = ()
	destructive: bool = False
	billable: bool = False
	# True if the execution function takes the previewed version as `expected_version`.
	versioned: bool = False
	# Pre-check of a write tool. It calls no Frappe document method. When it is set, the handler
	# takes only what the pre-check returned. See `proposals._execute` for the boundary.
	prepare: Callable[..., Any] | None = None
	# JSON Schema of a successful result. Published as `outputSchema`.
	output_schema: dict | None = None

	@cached_property
	def input_schema(self) -> dict:
		schema = self.arguments.model_json_schema(schema_generator=CompactJsonSchema)
		schema.setdefault("type", "object")
		schema.setdefault("properties", {})
		schema["additionalProperties"] = False
		return schema

	def definition(self) -> dict:
		annotations = (
			{"readOnlyHint": True}
			if self.kind == "read"
			else {"readOnlyHint": False, "destructiveHint": self.destructive}
		)
		definition = {
			"name": self.name,
			"description": self.description,
			"inputSchema": self.input_schema,
			"annotations": annotations,
		}
		if self.output_schema is not None:
			definition["outputSchema"] = self.output_schema
		return definition

	def visible(self) -> bool:
		return not self.roles or bool(set(self.roles) & set(frappe.get_roles()))


# Pre-check of every built-in write tool, by tool name.
PREPARE = {
	"create_document": "prepare_create",
	"update_document": "prepare_update",
	"submit_document": "prepare_submit",
	"cancel_document": "prepare_cancel",
	"delete_document": "prepare_delete",
	"add_custom_field": "prepare_custom_field",
	"set_field_property": "prepare_field_property",
	"set_role_permission": "prepare_role_permission",
	"assign_role": "prepare_assign_role",
	"remove_role": "prepare_remove_role",
	"purge_action_log": "prepare_purge",
}


def builtin_tools() -> tuple[AiTool, ...]:
	"""Built-in tools. Every write tool is paired with its pre-check."""
	from platform_core.yapay_zeka.tools import admin, results, write

	tools = []
	for tool in _builtin_tools():
		tool = replace(tool, output_schema=results.schema_for(tool.name, tool.kind))
		if tool.kind == "write":
			module = admin if tool.tool_class == "admin" else write
			tool = replace(tool, prepare=getattr(module, PREPARE[tool.name]))
		tools.append(tool)
	return tuple(tools)


def _builtin_tools() -> tuple[AiTool, ...]:
	from platform_core.yapay_zeka import proposals
	from platform_core.yapay_zeka.tools import admin, definition, read, write

	target = write.DocumentTargetArguments
	pending = " Nothing is written until a human approves the proposal."
	return (
		AiTool(
			"search_doctypes",
			"Search DocType names the user may read. Child tables are left out.",
			definition.SearchDoctypesArguments,
			definition.search_doctypes,
			"definition",
		),
		AiTool(
			"get_doctype_schema",
			"Get the fields of a DocType with their descriptions, and what the user may do with it. "
			"Secret fields are listed with secret=true and never carry a value.",
			definition.GetDoctypeSchemaArguments,
			definition.get_doctype_schema,
			"definition",
		),
		AiTool(
			"list_documents",
			"List documents the user may read. A filter is a value or an [operator, value] pair.",
			read.ListDocumentsArguments,
			read.list_documents,
			"read",
		),
		AiTool(
			"get_document",
			"Get one document with its child tables. Fields the user may not read are left out.",
			read.GetDocumentArguments,
			read.get_document,
			"read",
		),
		AiTool(
			"run_report",
			"Run a report the user may run and return its columns and rows.",
			read.RunReportArguments,
			read.run_report,
			"read",
		),
		AiTool(
			"create_document",
			"Propose a new document." + pending,
			write.CreateDocumentArguments,
			write.write_create,
			"write",
			"write",
			write.preview_create,
		),
		AiTool(
			"update_document",
			"Propose changes to a document." + pending,
			write.UpdateDocumentArguments,
			write.write_update,
			"write",
			"write",
			write.preview_update,
			destructive=True,
			versioned=True,
		),
		AiTool(
			"submit_document",
			"Propose submitting a draft document." + pending,
			target,
			write.write_submit,
			"write",
			"write",
			write.preview_submit,
			destructive=True,
			versioned=True,
		),
		AiTool(
			"cancel_document",
			"Propose cancelling a submitted document." + pending,
			target,
			write.write_cancel,
			"write",
			"write",
			write.preview_cancel,
			destructive=True,
			versioned=True,
		),
		AiTool(
			"delete_document",
			"Propose deleting a document." + pending,
			target,
			write.write_delete,
			"write",
			"write",
			write.preview_delete,
			destructive=True,
			versioned=True,
		),
		AiTool(
			"get_proposal",
			"Read the status and result of a proposal the user opened. A result of unknown means the "
			"outcome is not known. Do not repeat the action. Ask the user to check and resolve it.",
			proposals.GetProposalArguments,
			proposals.read_for_model,
			"flow",
		),
		*(
			AiTool(
				name,
				description + " Admin only." + pending,
				arguments,
				handler,
				"admin",
				"write",
				preview,
				roles=(admin.ADMIN_ROLE,),
				destructive=destructive,
				versioned=name != "purge_action_log",
			)
			for name, description, arguments, handler, preview, destructive in (
				(
					"add_custom_field",
					"Propose a new custom field on a DocType. A description is required.",
					admin.AddCustomFieldArguments,
					admin.write_custom_field,
					admin.preview_custom_field,
					False,
				),
				(
					"set_field_property",
					"Propose a change to one display or validation property of a field.",
					admin.SetFieldPropertyArguments,
					admin.write_field_property,
					admin.preview_field_property,
					True,
				),
				(
					"set_role_permission",
					"Propose a change to what a role may do with a DocType at one permission level.",
					admin.SetRolePermissionArguments,
					admin.write_role_permission,
					admin.preview_role_permission,
					True,
				),
				(
					"assign_role",
					"Propose giving a role to a user. Protected roles cannot be given through AI.",
					admin.UserRoleArguments,
					admin.write_assign_role,
					admin.preview_assign_role,
					True,
				),
				(
					"remove_role",
					"Propose taking a role away from a user.",
					admin.UserRoleArguments,
					admin.write_remove_role,
					admin.preview_remove_role,
					True,
				),
				(
					"purge_action_log",
					"Propose deleting AI action logs and proposals older than the retention period. "
					"Cannot be undone.",
					admin.PurgeActionLogArguments,
					admin.write_purge,
					admin.preview_purge,
					True,
				),
			)
		),
	)


def app_tools(taken: set[str]) -> list[AiTool]:
	"""Load the tools apps declare. An invalid declaration is not loaded and lands in the error log."""
	tools = []
	for path in frappe.get_hooks("ai_tools") or []:
		app = path.split(".")[0]
		try:
			declarations = list(frappe.get_attr(path)() or [])
		except Exception as error:
			_report_once(f"ai_tools: {path} could not be loaded", error)
			continue
		for declaration in declarations:
			try:
				tool = build_app_tool(app, declaration, taken)
			except Exception as error:
				# A broken declaration does not stop the other tools. Only that tool is not loaded.
				_report_once(f"ai_tools: invalid declaration in {app}", error)
				continue
			taken.add(tool.name)
			tools.append(tool)
	return tools


_reported: set[str] = set()


def _report_once(title: str, error: Exception) -> None:
	"""Write the same error to the error log once per process. The hook is read on every request."""
	key = f"{title}: {error!r}"
	if key not in _reported:
		_reported.add(key)
		frappe.log_error(title=title, message=repr(error))


def build_app_tool(app: str, declaration: dict, taken: set[str]) -> AiTool:
	"""Validate the declaration. Raises `ValueError` for a declaration that breaks the rules."""
	from platform_core.yapay_zeka.tools import results

	if not isinstance(declaration, dict) or set(declaration) - DECLARATION_KEYS:
		raise ValueError("declaration has unknown keys")
	short_name = declaration.get("name")
	if not isinstance(short_name, str) or not APP_TOOL_NAME.match(short_name):
		raise ValueError(f"tool name {short_name!r} does not match the pattern")
	name = f"{app}_{short_name}"
	if name in taken:
		raise ValueError(f"tool name {name} is already taken")
	if not isinstance(declaration.get("description"), str) or not declaration["description"].strip():
		raise ValueError(f"{name}: description is required")
	kind = declaration.get("kind")
	if kind not in ("read", "write"):
		raise ValueError(f"{name}: kind must be read or write")
	if not isinstance(declaration.get("arguments"), str) or not isinstance(declaration.get("handler"), str):
		raise ValueError(f"{name}: arguments and handler must be dotted paths")

	# The path comes from the hooks.py file of the installed app, not from user input (G-10).
	arguments = frappe.get_attr(declaration["arguments"])
	if not (isinstance(arguments, type) and issubclass(arguments, BaseModel)):
		raise ValueError(f"{name}: arguments must be a pydantic model")
	if arguments.model_config.get("extra") != "forbid":
		raise ValueError(f"{name}: the arguments model must forbid unknown fields")
	if set(arguments.model_fields) & policy.FORBIDDEN_ARGUMENT_NAMES:
		raise ValueError(f"{name}: approval-like argument names are not allowed")

	preview = declaration.get("preview")
	if kind == "write" and not preview:
		raise ValueError(f"{name}: a write tool needs a preview function")
	prepare = declaration.get("prepare")
	if (prepare or declaration.get("versioned")) and kind != "write":
		raise ValueError(f"{name}: prepare and versioned belong to write tools")
	if prepare is not None and not isinstance(prepare, str):
		raise ValueError(f"{name}: prepare must be a dotted path")
	roles = declaration.get("roles") or ()
	if not all(isinstance(role, str) for role in roles):
		raise ValueError(f"{name}: roles must be a list of role names")

	return AiTool(
		name=name,
		description=declaration["description"],
		arguments=arguments,
		handler=frappe.get_attr(declaration["handler"]),
		tool_class="app",
		kind=kind,
		preview=frappe.get_attr(preview) if kind == "write" else None,
		roles=tuple(roles),
		destructive=bool(declaration.get("destructive")),
		billable=bool(declaration.get("billable")),
		output_schema=results.APPROVAL_REQUIRED if kind == "write" else None,
		# Optional for a write tool: its own pre-check, and a version check done by the layer.
		prepare=frappe.get_attr(prepare) if prepare else None,
		versioned=bool(declaration.get("versioned")),
	)


def all_tools() -> list[AiTool]:
	"""The tool list is built once per request."""
	cached = getattr(frappe.local, "yz_tools", None)
	if cached is None:
		tools = list(builtin_tools())
		cached = frappe.local.yz_tools = tools + app_tools({tool.name for tool in tools})
	return cached


def find(name: str) -> AiTool | None:
	return next((tool for tool in all_tools() if tool.name == name), None)


def definitions() -> list[dict]:
	"""The tool list narrowed by the user's roles (G-84)."""
	return [tool.definition() for tool in all_tools() if tool.visible()]


__all__ = ["AiTool", "ToolArguments", "all_tools", "definitions", "find"]
