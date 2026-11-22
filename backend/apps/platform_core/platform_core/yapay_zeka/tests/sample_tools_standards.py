"""Sample app tools for the rules found by the standards self-audit. Not used in production."""

import frappe
from pydantic import BaseModel, ConfigDict

DOCTYPE = "YZ Test Kayit"
PATH = "platform_core.yapay_zeka.tests.sample_tools_standards."
FLAG = "ai_test_preview_must_fail"


class TitleArguments(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")

	name: str
	title: str


def preview_that_writes_then_fails(name: str, title: str) -> dict:
	"""On the second run this preview changes the record and then refuses."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if frappe.cache.get_value(FLAG):
		frappe.db.set_value(DOCTYPE, name, "title", "Left by a failed preview")
		frappe.throw("The preview refuses now", frappe.ValidationError)
	return {"summary": f"Set the title of {name}"}


def set_title(name: str, title: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.title = title
	doc.save()
	return {"name": doc.name}


def declare() -> list[dict]:
	return [
		{
			"name": "writes_in_preview",
			"description": "Preview writes and then refuses.",
			"arguments": PATH + "TitleArguments",
			"kind": "write",
			"handler": PATH + "set_title",
			"preview": PATH + "preview_that_writes_then_fails",
		}
	]
