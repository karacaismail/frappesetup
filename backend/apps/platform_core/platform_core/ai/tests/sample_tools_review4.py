"""Sample app tools for the rules of the fourth independent review. Not used in production."""

import frappe
from pydantic import BaseModel, ConfigDict

DOCTYPE = "YZ Test Kayit"
PATH = "platform_core.ai.tests.sample_tools_review4."
PRICE_KEY = "ai_test_preview_price"
TARGET_KEY = "ai_test_preview_target"


class TitleArguments(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")

	name: str
	title: str


def set_title(name: str, title: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	doc.title = title
	doc.save()
	return {"name": doc.name}


def _priced(name: str, *, with_target: bool) -> dict:
	"""A preview whose amount comes from outside the target record, so the record's version does not move."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	spec = {
		"summary": f"Charge for {name}",
		"details": {"price": frappe.cache.get_value(PRICE_KEY) or 100},
	}
	if with_target:
		target = frappe.cache.get_value(TARGET_KEY) or name
		spec.update(target_doctype=DOCTYPE, target_name=target, target_version=str(doc.modified))
	return spec


def preview_priced(name: str, title: str) -> dict:
	return _priced(name, with_target=False)


def preview_priced_versioned(name: str, title: str) -> dict:
	return _priced(name, with_target=True)


def preview_with_numeric_label(name: str, title: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	return {
		"summary": f"Set the title of {name}",
		"changes": [{"fieldname": "title", "label": 5, "new": title}],
	}


def declare() -> list[dict]:
	base = {"arguments": PATH + "TitleArguments", "kind": "write", "handler": PATH + "set_title"}
	return [
		{
			**base,
			"name": "priced",
			"description": "Preview shows a price.",
			"preview": PATH + "preview_priced",
		},
		{
			**base,
			"name": "priced_versioned",
			"description": "Preview shows a price and guards the target version.",
			"versioned": True,
			"preview": PATH + "preview_priced_versioned",
		},
		{
			**base,
			"name": "numeric_label",
			"description": "Preview returns a label of the wrong type.",
			"preview": PATH + "preview_with_numeric_label",
		},
	]
