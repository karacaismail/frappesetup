"""Sample app tools whose errors carry a value that must not leave the server. Not used in production."""

import frappe
from pydantic import BaseModel, ConfigDict

DOCTYPE = "YZ Test Kayit"
PATH = "platform_core.yapay_zeka.tests.sample_tools_errors."
# A made-up value that stands for personal data inside an error text.
MARKER = "leak-marker-48151623"


class Arguments(BaseModel):
	model_config = ConfigDict(strict=True, extra="forbid")

	name: str


def preview_ok(name: str) -> dict:
	frappe.get_doc(DOCTYPE, name).check_permission("write")
	return {"summary": f"Touch {name}"}


def refuse_validation(name: str) -> dict:
	frappe.throw(f"Invalid value {MARKER}", frappe.ValidationError)


def refuse_permission(name: str) -> dict:
	raise frappe.PermissionError(f"No access for {MARKER}")


def refuse_missing(name: str) -> dict:
	raise frappe.DoesNotExistError(f"Nothing called {MARKER}")


def declare() -> list[dict]:
	base = {"arguments": PATH + "Arguments", "kind": "write", "handler": PATH + "refuse_validation"}
	return [
		{
			**base,
			"name": "leaky_validation",
			"description": "Preview refuses.",
			"preview": PATH + "refuse_validation",
		},
		{
			**base,
			"name": "leaky_permission",
			"description": "Preview refuses.",
			"preview": PATH + "refuse_permission",
		},
		{
			**base,
			"name": "leaky_missing",
			"description": "Preview refuses.",
			"preview": PATH + "refuse_missing",
		},
		{**base, "name": "leaky_handler", "description": "Handler refuses.", "preview": PATH + "preview_ok"},
		{
			**base,
			"name": "leaky_permission_handler",
			"description": "Handler refuses.",
			"preview": PATH + "preview_ok",
			"handler": PATH + "refuse_permission",
		},
	]
