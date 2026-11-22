"""Validate shell query parameters before applying the read policy."""

from typing import Literal

import frappe
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as QueryValidationError

FRAMEWORK_PARAMETERS = {"cmd", "_lang"}


class BootstrapQuery(BaseModel):
	model_config = ConfigDict(extra="forbid")


class MetadataQuery(BootstrapQuery):
	doctype: str
	surface: Literal["web", "mobile"] = "web"


def validate_query(schema: type[BootstrapQuery]) -> None:
	query = {key: value for key, value in frappe.form_dict.items() if key not in FRAMEWORK_PARAMETERS}
	try:
		schema.model_validate(query)
		return
	except QueryValidationError:
		pass
	frappe.throw(
		frappe._("The request has invalid parameters.", context="shell.request"),
		frappe.ValidationError,
	)
