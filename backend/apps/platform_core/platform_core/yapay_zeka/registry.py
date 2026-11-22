"""Araç kaydı: yerleşik araçlar ve uygulamaların `ai_tools` kancasıyla bildirdikleri (G-105)."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import frappe
from frappe.mcp.tools import CompactJsonSchema, ToolArguments
from pydantic import BaseModel

from platform_core.yapay_zeka import policy

APP_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
DECLARATION_KEYS = frozenset(
	{"name", "description", "arguments", "kind", "roles", "destructive", "billable", "handler", "preview"}
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
	extra: dict = field(default_factory=dict)

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
		return {
			"name": self.name,
			"description": self.description,
			"inputSchema": self.input_schema,
			"annotations": annotations,
		}

	def visible(self) -> bool:
		return not self.roles or bool(set(self.roles) & set(frappe.get_roles()))


def builtin_tools() -> tuple[AiTool, ...]:
	from platform_core.yapay_zeka import proposals
	from platform_core.yapay_zeka.tools import definition, read, write

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
			write.run_create,
			"write",
			"write",
			write.preview_create,
		),
		AiTool(
			"update_document",
			"Propose changes to a document." + pending,
			write.UpdateDocumentArguments,
			write.run_update,
			"write",
			"write",
			write.preview_update,
			destructive=True,
		),
		AiTool(
			"submit_document",
			"Propose submitting a draft document." + pending,
			target,
			write.run_submit,
			"write",
			"write",
			write.preview_submit,
			destructive=True,
		),
		AiTool(
			"cancel_document",
			"Propose cancelling a submitted document." + pending,
			target,
			write.run_cancel,
			"write",
			"write",
			write.preview_cancel,
			destructive=True,
		),
		AiTool(
			"delete_document",
			"Propose deleting a document." + pending,
			target,
			write.run_delete,
			"write",
			"write",
			write.preview_delete,
			destructive=True,
		),
		AiTool(
			"get_proposal",
			"Read the status and result of a proposal the user opened. A result of unknown means the "
			"outcome is not known. Do not repeat the action. Ask the user to check and resolve it.",
			proposals.GetProposalArguments,
			proposals.read_for_model,
			"flow",
		),
	)


def app_tools(taken: set[str]) -> list[AiTool]:
	"""Uygulamaların bildirdiği araçları yükler. Geçersiz bildirim yüklenmez ve hata kaydına düşer."""
	tools = []
	for path in frappe.get_hooks("ai_tools") or []:
		app = path.split(".")[0]
		try:
			declarations = frappe.get_attr(path)()
		except Exception:
			frappe.log_error(title=f"ai_tools: {path} could not be loaded")
			continue
		for declaration in declarations or []:
			try:
				tool = build_app_tool(app, declaration, taken)
			except (ValueError, TypeError, ImportError, AttributeError) as error:
				frappe.log_error(title=f"ai_tools: invalid declaration in {app}", message=str(error))
				continue
			taken.add(tool.name)
			tools.append(tool)
	return tools


def build_app_tool(app: str, declaration: dict, taken: set[str]) -> AiTool:
	"""Bildirimi doğrular. Kural dışı bildirimde `ValueError` verir."""
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

	# Yol kullanıcı girdisinden değil, kurulu uygulamanın hooks.py dosyasından gelir (G-10).
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
	)


def all_tools() -> list[AiTool]:
	tools = list(builtin_tools())
	return tools + app_tools({tool.name for tool in tools})


def find(name: str) -> AiTool | None:
	return next((tool for tool in all_tools() if tool.name == name), None)


def definitions() -> list[dict]:
	"""Kullanıcının rollerine göre daraltılmış araç listesi (G-84)."""
	return [tool.definition() for tool in all_tools() if tool.visible()]


__all__ = ["AiTool", "ToolArguments", "all_tools", "definitions", "find"]
