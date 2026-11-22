"""Declare approval-gated management tools for the gateway registry."""

from decimal import Decimal
from typing import Annotated, Literal

import frappe
from frappe import _
from pydantic import BaseModel, ConfigDict, Field

from platform_core.model_gecidi import gateway
from platform_core.model_gecidi.doctype.ai_api.ai_api import clear_api_credential
from platform_core.model_gecidi.doctype.validation import validate_url
from platform_core.model_gecidi.policy import MANAGERS

API_DOCTYPE = "AI API"
ACCOUNT_DOCTYPE = "AI Account"
MODULE_PATH = "platform_core.model_gecidi.management_tools."
CONNECTION_FIELDS = frozenset({"base_url", "auth_type", "oauth_token_url", "oauth_client_id"})

Identifier = Annotated[str, Field(min_length=1, max_length=140)]
Address = Annotated[str, Field(max_length=2048)]
Money = Annotated[str, Field(max_length=22, pattern=r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,9})?$")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Rate = Annotated[int, Field(ge=0, le=2_147_483_647)]
AuthType = Literal["none", "api_key", "bearer", "oauth_client_credentials"]


class Arguments(BaseModel):
	model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class ApiSettings(Arguments):
	base_url: Address | None = None
	auth_type: AuthType | None = None
	oauth_token_url: Address | None = None
	oauth_client_id: Identifier | None = None
	allowed_models: list[Identifier] | None = Field(default=None, max_length=100)
	requests_per_minute: Rate | None = None
	tokens_per_minute: Rate | None = None
	priority: Rate | None = None
	weight: Rate | None = None


class CreateApi(ApiSettings):
	account: Identifier
	api_name: Identifier


class UpdateApi(ApiSettings):
	name: Identifier
	api_name: Identifier | None = None


class AccountSettings(Arguments):
	organization_id: Identifier | None = None
	project_id: Identifier | None = None
	has_monthly_budget: bool | None = None
	monthly_budget: Money | None = None
	currency: Currency | None = None
	enabled: bool | None = None


class CreateAccount(AccountSettings):
	provider: Identifier
	account_name: Identifier


class UpdateAccount(AccountSettings):
	name: Identifier
	account_name: Identifier | None = None


def _require_manager():
	if frappe.session.user == "Guest" or not MANAGERS.intersection(frappe.get_roles()):
		frappe.throw(_("Gateway registry management requires a manager role."), frappe.PermissionError)


def _validated(model, arguments):
	return model.model_validate(arguments).model_dump(exclude_none=True)


def _check_api_values(values):
	validate_url(values.get("base_url"), "Base URL")
	validate_url(values.get("oauth_token_url"), "OAuth Token URL", https_only=True)


def _new_doc(doctype, values):
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.check_permission("create")
	return doc


def _load(doctype, name, *, for_update=False):
	doc = frappe.get_doc(doctype, name, for_update=for_update)
	doc.check_permission("write")
	return doc


def _connection_changed(doc, values):
	return any((doc.get(field) or "") != (values[field] or "") for field in CONNECTION_FIELDS & values.keys())


def _preview(doctype, action, values, doc=None, *, reset_credential=False):
	changes = [{"fieldname": field, "new": value} for field, value in sorted(values.items())]
	if reset_credential:
		changes.append({"fieldname": "enabled", "new": False})
	return {
		"action": action,
		"summary": (
			_("Review the gateway registry update.")
			if action == "update"
			else _("Review the new gateway registry record.")
		),
		"target_doctype": doctype,
		"target_name": doc.name if doc else None,
		"target_version": str(doc.modified) if doc else None,
		"changes": changes,
		"details": {"credential_will_be_cleared": reset_credential} if doctype == API_DOCTYPE else {},
	}


def _save_account(doc, values, *, create=False):
	budget = values.get("monthly_budget")
	if not create and budget is None:
		budget = gateway.lock_row(ACCOUNT_DOCTYPE, doc.name, ("monthly_budget",)).monthly_budget
	doc.insert() if create else doc.save()
	if budget is not None:
		# Frappe normalizes Currency fields through float on Document save.
		# Preserve the new or existing exact decimal under the same row lock.
		frappe.db.set_value(
			ACCOUNT_DOCTYPE, doc.name, "monthly_budget", Decimal(budget), update_modified=False
		)
	return {"name": doc.name}


def preview_create_api(**arguments):
	_require_manager()
	values = _validated(CreateApi, arguments)
	_check_api_values(values)
	frappe.get_doc(ACCOUNT_DOCTYPE, values["account"]).check_permission("read")
	values["enabled"] = False
	_new_doc(API_DOCTYPE, values)
	return _preview(API_DOCTYPE, "create", values)


def create_api(**arguments):
	_require_manager()
	values = _validated(CreateApi, arguments)
	_check_api_values(values)
	frappe.get_doc(ACCOUNT_DOCTYPE, values["account"]).check_permission("read")
	doc = _new_doc(API_DOCTYPE, {**values, "enabled": False})
	doc.insert()
	return {"name": doc.name}


def preview_update_api(**arguments):
	_require_manager()
	values = _validated(UpdateApi, arguments)
	doc = _load(API_DOCTYPE, values.pop("name"))
	_check_api_values(values)
	return _preview(API_DOCTYPE, "update", values, doc, reset_credential=_connection_changed(doc, values))


def update_api(**arguments):
	_require_manager()
	values = _validated(UpdateApi, arguments)
	doc = _load(API_DOCTYPE, values.pop("name"), for_update=True)
	_check_api_values(values)
	reset_credential = _connection_changed(doc, values)
	doc.update(values)
	if reset_credential:
		doc.enabled = False
	doc.save()
	if reset_credential:
		clear_api_credential(doc.name)
		doc.add_comment("Info", _("Model gateway API credential cleared."))
	return {"name": doc.name}


def preview_create_account(**arguments):
	_require_manager()
	values = _validated(CreateAccount, arguments)
	frappe.get_doc("AI Provider", values["provider"]).check_permission("read")
	_new_doc(ACCOUNT_DOCTYPE, values)
	return _preview(ACCOUNT_DOCTYPE, "create", values)


def create_account(**arguments):
	_require_manager()
	values = _validated(CreateAccount, arguments)
	frappe.get_doc("AI Provider", values["provider"]).check_permission("read")
	return _save_account(_new_doc(ACCOUNT_DOCTYPE, values), values, create=True)


def preview_update_account(**arguments):
	_require_manager()
	values = _validated(UpdateAccount, arguments)
	doc = _load(ACCOUNT_DOCTYPE, values.pop("name"))
	return _preview(ACCOUNT_DOCTYPE, "update", values, doc)


def update_account(**arguments):
	_require_manager()
	values = _validated(UpdateAccount, arguments)
	doc = _load(ACCOUNT_DOCTYPE, values.pop("name"), for_update=True)
	doc.update(values)
	return _save_account(doc, values)


def declare():
	"""Register registry writes with human approval in the AI layer."""
	roles = sorted(MANAGERS)
	return [
		{
			"name": "create_ai_api",
			"description": "Create a disabled model provider connection.",
			"kind": "write",
			"roles": roles,
			"arguments": MODULE_PATH + "CreateApi",
			"handler": MODULE_PATH + "create_api",
			"preview": MODULE_PATH + "preview_create_api",
			"versioned": False,
			"destructive": False,
		},
		{
			"name": "update_ai_api",
			"description": "Update a provider connection and clear its stored credential if its destination changes.",
			"kind": "write",
			"roles": roles,
			"arguments": MODULE_PATH + "UpdateApi",
			"handler": MODULE_PATH + "update_api",
			"preview": MODULE_PATH + "preview_update_api",
			"versioned": True,
			"destructive": True,
		},
		{
			"name": "create_ai_account",
			"description": "Create a model provider account.",
			"kind": "write",
			"roles": roles,
			"arguments": MODULE_PATH + "CreateAccount",
			"handler": MODULE_PATH + "create_account",
			"preview": MODULE_PATH + "preview_create_account",
			"versioned": False,
			"destructive": False,
		},
		{
			"name": "update_ai_account",
			"description": "Update model provider account settings.",
			"kind": "write",
			"roles": roles,
			"arguments": MODULE_PATH + "UpdateAccount",
			"handler": MODULE_PATH + "update_account",
			"preview": MODULE_PATH + "preview_update_account",
			"versioned": True,
			"destructive": False,
		},
	]
