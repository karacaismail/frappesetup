"""Sample app tools of the risk level tests (AJA-1001). Not used in production."""

import frappe
from pydantic import BaseModel, ConfigDict

DOCTYPE = "YZ Test Kayit"

PATH = "platform_core.ai.tests.sample_tools."
OWN = "platform_core.ai.tests.sample_tools_risk."


class Strict(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")


class RiskArguments(Strict):
	name: str
	risk_level: str = "R0"


class NoteArguments(Strict):
	name: str
	internal_note: str


def preview_internal_note(name: str, internal_note: str) -> dict:
	"""Shows the old and new value of a permlevel 1 field (AJA-1077)."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	return {
		"summary": f"Set the internal note of {name}",
		"target_doctype": DOCTYPE,
		"target_name": name,
		"target_version": str(doc.modified),
		"changes": [{"fieldname": "internal_note", "old": doc.internal_note, "new": internal_note}],
	}


def set_internal_note(name: str, internal_note: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	doc.internal_note = internal_note
	doc.save()
	return {"name": doc.name}


def _title_tool(name: str, **extra) -> dict:
	return {
		"name": name,
		"description": "Set the title of a test record.",
		"arguments": PATH + "TitleArguments",
		"kind": "write",
		"handler": PATH + "set_title",
		"preview": PATH + "preview_title",
		**extra,
	}


def declare() -> list[dict]:
	return [
		# Declares a level lower than its class gives. The computed level wins.
		_title_tool("low_declared_delete", destructive=True, risk_level="R0"),
		# Declares a level higher than its class gives. The declared level wins.
		_title_tool("high_declared_note", risk_level="R3"),
		# An R3 tool whose preview shows a permlevel 1 field (AJA-1077).
		{
			"name": "high_internal_note",
			"description": "Set the internal note of a test record.",
			"arguments": OWN + "NoteArguments",
			"kind": "write",
			"handler": OWN + "set_internal_note",
			"preview": OWN + "preview_internal_note",
			"risk_level": "R3",
		},
		# Declares nothing. The level comes from its class.
		_title_tool("plain_note"),
		# Invalid declarations. The layer must not load them.
		_title_tool("unknown_level", risk_level="R9"),
		{
			"name": "level_in_arguments",
			"description": "Invalid: the model must not send the risk level.",
			"arguments": OWN + "RiskArguments",
			"kind": "read",
			"handler": PATH + "count_records",
		},
	]
