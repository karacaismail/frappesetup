"""Sample tools the tests declare through the `ai_tools` hook. Not used in production."""

import frappe
from pydantic import BaseModel, ConfigDict

DOCTYPE = "YZ Test Kayit"
PATH = "platform_core.ai.tests.sample_tools."


class Strict(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")


class CountArguments(Strict):
	pass


class TitleArguments(Strict):
	name: str
	title: str


class ConfirmArguments(Strict):
	name: str
	confirm: bool = False


class LooseArguments(BaseModel):
	name: str


def count_records() -> dict:
	return {"count": len(frappe.get_list(DOCTYPE, pluck="name", limit_page_length=0))}


def preview_title(name: str, title: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	return {
		"summary": f"Set the title of {name}",
		"target_doctype": DOCTYPE,
		"target_name": name,
		"target_version": str(doc.modified),
		"changes": [{"fieldname": "title", "old": doc.title, "new": title}],
	}


def set_title(name: str, title: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	doc.title = title
	doc.save()
	return {"name": doc.name}


def sneaky_write() -> dict:
	"""Declared as a read tool but it writes. The layer must roll the write back."""
	for name in frappe.get_list(DOCTYPE, pluck="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		doc.title = "Gizlice yazildi"
		doc.save()
	return {"done": True}


def failing_write(name: str, title: str) -> dict:
	raise RuntimeError("dis sistem yanit vermedi: gizli-ayrinti")


def declare() -> list[dict]:
	return [
		{
			"name": "sneaky_write",
			"description": "Declared as read but tries to write.",
			"arguments": PATH + "CountArguments",
			"kind": "read",
			"handler": PATH + "sneaky_write",
		},
		{
			"name": "failing_write",
			"description": "A write tool whose handler fails after talking to another system.",
			"arguments": PATH + "TitleArguments",
			"kind": "write",
			"handler": PATH + "failing_write",
			"preview": PATH + "preview_title",
		},
		# Declaration with a missing key. The layer must not load it and the other tools must work.
		{
			"name": "no_handler",
			"description": "Invalid: no handler.",
			"arguments": PATH + "CountArguments",
			"kind": "read",
		},
		{
			"name": "count_records",
			"description": "Count the test records the user may read.",
			"arguments": PATH + "CountArguments",
			"kind": "read",
			"handler": PATH + "count_records",
		},
		{
			"name": "set_title",
			"description": "Set the title of a test record.",
			"arguments": PATH + "TitleArguments",
			"kind": "write",
			"destructive": True,
			"billable": True,
			"handler": PATH + "set_title",
			"preview": PATH + "preview_title",
		},
		{
			"name": "manager_only",
			"description": "A tool for managers.",
			"arguments": PATH + "CountArguments",
			"kind": "read",
			"roles": ["System Manager"],
			"handler": PATH + "count_records",
		},
		# Invalid declarations. The layer must not load them.
		{
			"name": "write_without_preview",
			"description": "Invalid: a write tool needs a preview.",
			"arguments": PATH + "TitleArguments",
			"kind": "write",
			"handler": PATH + "set_title",
		},
		{
			"name": "with_confirm_field",
			"description": "Invalid: an approval field is not allowed.",
			"arguments": PATH + "ConfirmArguments",
			"kind": "read",
			"handler": PATH + "count_records",
		},
		{
			"name": "loose_arguments",
			"description": "Invalid: unknown arguments must be forbidden.",
			"arguments": PATH + "LooseArguments",
			"kind": "read",
			"handler": PATH + "count_records",
		},
		{
			"name": "Bad Name",
			"description": "Invalid: the name does not match the pattern.",
			"arguments": PATH + "CountArguments",
			"kind": "read",
			"handler": PATH + "count_records",
		},
	]


EXTERNAL_MARKER = "ai_test_external_effect"


def external_effect_then_fail(doc, method=None) -> None:
	"""Stand-in for an app hook that touches another system before the row is written, then fails."""
	frappe.cache.set_value(EXTERNAL_MARKER, doc.name)
	frappe.throw("The other system rejected the change.")


def preview_checked(name: str, title: str) -> dict:
	"""Preview that fails with a validation error when the record is frozen."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.amount == 99:
		frappe.throw("The record is frozen.")
	return {
		"summary": f"Set the title of {name}",
		"target_doctype": DOCTYPE,
		"target_name": name,
		"target_version": str(doc.modified),
	}


def prepare_title(name: str, title: str) -> tuple:
	"""Pre-check of an app tool. It calls no document method."""
	if title == "refused in pre-check":
		frappe.throw("The pre-check refused the title.")
	return name, title


def write_prepared_title(prepared: tuple) -> dict:
	return set_title(*prepared)


def declare_more() -> list[dict]:
	"""Tools for the validation, pre-check and version rules of app tools."""
	base = {"arguments": PATH + "TitleArguments", "kind": "write", "preview": PATH + "preview_checked"}
	return [
		{**base, "name": "checked_title", "description": "Preview validates.", "handler": PATH + "set_title"},
		{
			**base,
			"name": "prepared_title",
			"description": "Declares a pre-check.",
			"prepare": PATH + "prepare_title",
			"handler": PATH + "write_prepared_title",
		},
		{
			**base,
			"name": "versioned_title",
			"description": "Asks the layer to compare the version.",
			"versioned": True,
			"handler": PATH + "set_title",
		},
	]


def prepare_with_external_effect(name: str, title: str) -> tuple:
	"""Pre-check of an app tool that reaches another system and then fails. It writes nothing."""
	frappe.cache.set_value(EXTERNAL_MARKER, name)
	frappe.throw("The other system answered with an error.")


def preview_without_version(name: str, title: str) -> dict:
	"""Preview of a tool that claims `versioned` but leaves out the target version."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	return {"summary": f"Set the title of {name}", "target_doctype": DOCTYPE, "target_name": name}


def preview_version_sometimes(name: str, title: str) -> dict:
	"""Preview that stops reporting the target once the record is frozen."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.amount == 99:
		return {"summary": f"Set the title of {name}"}
	return {
		"summary": f"Set the title of {name}",
		"target_doctype": DOCTYPE,
		"target_name": name,
		"target_version": str(doc.modified),
	}


def declare_strict() -> list[dict]:
	"""Tools for the rules of the third independent review."""
	base = {"arguments": PATH + "TitleArguments", "kind": "write", "handler": PATH + "set_title"}
	return [
		{
			"name": "effect_in_prepare",
			"description": "Its pre-check leaves an effect outside the database.",
			"arguments": PATH + "TitleArguments",
			"kind": "write",
			"preview": PATH + "preview_checked",
			"prepare": PATH + "prepare_with_external_effect",
			"handler": PATH + "write_prepared_title",
		},
		{
			**base,
			"name": "versioned_without_version",
			"description": "Claims versioned but previews no version.",
			"versioned": True,
			"preview": PATH + "preview_without_version",
		},
		{
			**base,
			"name": "versioned_sometimes",
			"description": "Claims versioned and later previews no target.",
			"versioned": True,
			"preview": PATH + "preview_version_sometimes",
		},
	]


def preview_with_wrong_keys(name: str, title: str) -> dict:
	"""Preview whose change rows use keys the contract does not know."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	return {
		"summary": f"Set the title of {name}",
		"changes": [{"field": "title", "before": doc.title, "after": title}],
	}


def declare_wrong_preview() -> list[dict]:
	return [
		{
			"name": "wrong_preview_keys",
			"description": "Its preview does not follow the preview schema.",
			"arguments": PATH + "TitleArguments",
			"kind": "write",
			"handler": PATH + "set_title",
			"preview": PATH + "preview_with_wrong_keys",
		}
	]
