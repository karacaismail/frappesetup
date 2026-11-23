"""Provider definitions, connection saving and the live connection check.

Provider definitions are data in provider_catalog.json. This module only knows
which record fields a definition may write to. Model names never appear here.
"""

import json
import re
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

import frappe
from frappe import _
from frappe.utils import now
from frappe.utils.password import get_decrypted_password

from platform_core.model_gateway import adapters, gateway, policy
from platform_core.model_gateway.doctype.validation import validate_url
from platform_core.model_gateway.policy import Denied

CATALOG_FILE = Path(__file__).with_name("provider_catalog.json")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
AUTH_TYPES = {"none", "api_key", "bearer", "oauth_client_credentials"}
KINDS = {"secret", "text", "url"}
# A definition may write only to these record fields. The secret goes only
# to the encrypted password field.
TARGETS = {
	"api.api_key": "secret",
	"api.base_url": "url",
	"api.oauth_token_url": "url",
	"api.oauth_client_id": "text",
	"account.organization_id": "text",
	"account.project_id": "text",
}
COMMON_FIELDS = (
	("account_name", "Account name", "account", "Name of the provider account in this site."),
	("api_name", "Connection name", "api", "Name of this API connection."),
)
MAX_LENGTH = {"secret": 4096, "text": 140, "url": 2048}
CHECK_TIMEOUT = 10
CHECK_CONNECT_TIMEOUT = 5
CHECK_STATUS = {
	"authentication": "invalid_credentials",
	"forbidden": "permission_denied",
	"rate_limit": "quota_exceeded",
	"connect_failed": "network_error",
	"timeout": "network_error",
	"endpoint_unavailable": "network_error",
	"configuration": "configuration_error",
}


class FieldsDenied(Denied):
	"""A request whose named connection fields failed validation."""

	def __init__(self, fields):
		super().__init__(400, "invalid_fields")
		self.fields = sorted(fields)


def _require(condition, message):
	if not condition:
		raise ValueError(message)


def _check_keys(item, required, optional=()):
	_require(isinstance(item, dict), "Expected an object")
	_require(set(required) <= set(item) <= {*required, *optional}, "Unexpected keys")


def _check_text(value):
	_require(isinstance(value, str) and value.strip() == value and value, "Expected text")


def _check_field(field):
	_check_keys(field, ("name", "label", "kind", "required", "target", "description"))
	_require(isinstance(field["name"], str) and IDENTIFIER.fullmatch(field["name"]), "Bad field name")
	_require(field["name"] not in {name for name, *_rest in COMMON_FIELDS}, "Reserved field name")
	_check_text(field["label"])
	_check_text(field["description"])
	_require(field["kind"] in KINDS, "Bad field kind")
	_require(type(field["required"]) is bool, "Bad required flag")
	_require(TARGETS.get(field["target"]) == field["kind"], "Bad field target")


def _check_provider(provider, categories):
	_check_keys(
		provider,
		("id", "category", "label", "description", "adapter", "default_url", "auth_type", "fields"),
	)
	_require(isinstance(provider["id"], str) and IDENTIFIER.fullmatch(provider["id"]), "Bad provider id")
	_require(provider["category"] in categories, "Unknown category")
	_check_text(provider["label"])
	_check_text(provider["description"])
	_require(provider["adapter"] in adapters.PATHS, "Unknown adapter")
	_require(provider["auth_type"] in AUTH_TYPES, "Unknown authentication type")
	default_url = provider["default_url"]
	_require(isinstance(default_url, str), "Bad default address")
	if default_url:
		parsed = urlsplit(default_url)
		_require(parsed.scheme == "https" and parsed.hostname and not parsed.query, "Bad default address")
	fields = provider["fields"]
	_require(isinstance(fields, list), "Bad field list")
	for field in fields:
		_check_field(field)
	names = [field["name"] for field in fields]
	targets = [field["target"] for field in fields]
	_require(len(set(names)) == len(names) and len(set(targets)) == len(targets), "Duplicate field")
	required = {field["target"] for field in fields if field["required"]}
	if provider["auth_type"] != "none":
		_require("api.api_key" in required, "Credential field missing")
	else:
		_require("api.api_key" not in targets, "Unexpected credential field")
	if provider["auth_type"] == "oauth_client_credentials":
		_require({"api.oauth_client_id", "api.oauth_token_url"} <= required, "OAuth fields missing")
	_require(default_url or "api.base_url" in required, "Address missing")


def validate_catalog(data):
	"""Raise ValueError when the provider catalog breaks its rules."""
	_check_keys(data, ("version", "categories", "providers"))
	_require(type(data["version"]) is int and data["version"] >= 1, "Bad version")
	_require(isinstance(data["categories"], list) and data["categories"], "Bad category list")
	categories = set()
	for category in data["categories"]:
		_check_keys(category, ("id", "label", "description"))
		_require(isinstance(category["id"], str) and IDENTIFIER.fullmatch(category["id"]), "Bad category")
		_check_text(category["label"])
		_check_text(category["description"])
		_require(category["id"] not in categories, "Duplicate category")
		categories.add(category["id"])
	_require(isinstance(data["providers"], list) and data["providers"], "Bad provider list")
	seen = set()
	for provider in data["providers"]:
		_check_provider(provider, categories)
		_require(provider["id"] not in seen, "Duplicate provider")
		seen.add(provider["id"])
	return data


@cache
def _catalog_text():
	return CATALOG_FILE.read_text(encoding="utf-8")


def provider_catalog_data():
	"""Return a fresh, validated copy of the shipped catalog."""
	try:
		return validate_catalog(json.loads(_catalog_text()))
	except (OSError, ValueError, RecursionError):
		raise Denied(503, "catalog_unavailable") from None


def _public_field(name, label, kind, required, scope, description):
	return {
		"name": name,
		"label": _(label),
		"kind": kind,
		"required": required,
		"scope": scope,
		"description": _(description),
	}


def provider_catalog():
	"""Return the definitions the connection form draws from, without storage details."""
	policy.require_user(managers_only=True)
	data = provider_catalog_data()
	common = [
		_public_field(name, label, "text", True, scope, description)
		for name, label, scope, description in COMMON_FIELDS
	]
	return {
		"version": data["version"],
		"categories": [
			{"id": item["id"], "label": _(item["label"]), "description": _(item["description"])}
			for item in data["categories"]
		],
		"providers": [
			{
				"id": provider["id"],
				"category": provider["category"],
				"label": _(provider["label"]),
				"description": _(provider["description"]),
				"auth_type": provider["auth_type"],
				"fields": [
					_public_field(
						field["name"],
						field["label"],
						field["kind"],
						field["required"],
						field["target"].partition(".")[0],
						field["description"],
					)
					for field in provider["fields"]
				],
				"common_fields": common,
			}
			for provider in data["providers"]
		],
	}


def provider_definition(provider_id):
	if not isinstance(provider_id, str):
		raise Denied(400, "unknown_provider")
	for provider in provider_catalog_data()["providers"]:
		if provider["id"] == provider_id:
			return provider
	raise Denied(400, "unknown_provider")


def _valid_url(value):
	try:
		validate_url(value, "Base URL")
	except frappe.ValidationError:
		return False
	finally:
		frappe.clear_messages()
	return True


def _valid_value(kind, value):
	if not isinstance(value, str) or len(value) > MAX_LENGTH[kind] or value.strip() != value:
		return False
	if kind == "secret":
		return value.isprintable() and not any(character.isspace() for character in value)
	if kind == "url":
		return _valid_url(value)
	return value.isprintable()


def parse_fields(definition, fields, *, new_account):
	"""Validate form values and map them to their record fields."""
	if not isinstance(fields, dict):
		raise Denied(400, "invalid_request")
	known = {field["name"]: field for field in definition["fields"]}
	invalid = {name if isinstance(name, str) else "?" for name in fields if name not in known}
	values = {}
	for name, field in known.items():
		value = fields.get(name)
		if value is None or value == "":
			if field["required"]:
				invalid.add(name)
			continue
		if not _valid_value(field["kind"], value) or (
			not new_account and field["target"].startswith("account.")
		):
			invalid.add(name)
			continue
		values[field["target"]] = value
	if invalid:
		raise FieldsDenied(invalid)
	return values


def _record_name(value):
	return isinstance(value, str) and 0 < len(value) <= 140 and value.strip() == value and value.isprintable()


def _provider_record(definition):
	existing = frappe.get_all(
		"PLT AI Provider",
		filters={"catalog_provider": definition["id"], "adapter": definition["adapter"]},
		pluck="name",
		order_by="creation asc",
		limit=1,
	)
	if existing:
		return existing[0]
	label = definition["label"]
	# Provider names are unique. A provider added by hand may already use the label.
	if frappe.db.exists("PLT AI Provider", {"provider_name": label}):
		label = f"{label} ({frappe.generate_hash(length=8)})"
	return (
		frappe.get_doc(
			{
				"doctype": "PLT AI Provider",
				"provider_name": label,
				"adapter": definition["adapter"],
				"default_url": definition["default_url"] or None,
				"catalog_provider": definition["id"],
			}
		)
		.insert()
		.name
	)


def _existing_account(name, provider):
	try:
		account = frappe.get_doc("PLT AI Account", name)
	except frappe.DoesNotExistError:
		raise frappe.PermissionError from None
	account.check_permission("write")
	if account.provider != provider:
		raise FieldsDenied(["account"])
	return account.name


def save_connection(provider, api_name, fields, account=None, account_name=None):
	"""Create an API connection from a catalog definition. Returns no secret."""
	policy.require_user(managers_only=True)
	definition = provider_definition(provider)
	if (
		not _record_name(api_name)
		or (account is None) == (account_name is None)
		or not _record_name(account if account is not None else account_name)
	):
		raise Denied(400, "invalid_request")
	values = parse_fields(definition, fields, new_account=account is None)
	provider_name = _provider_record(definition)
	if account is None:
		account = (
			frappe.get_doc(
				{
					"doctype": "PLT AI Account",
					"provider": provider_name,
					"account_name": account_name,
					**{
						key.partition(".")[2]: value
						for key, value in values.items()
						if key.startswith("account.")
					},
				}
			)
			.insert()
			.name
		)
	else:
		account = _existing_account(account, provider_name)
	api = frappe.get_doc(
		{
			"doctype": "PLT AI API",
			"account": account,
			"api_name": api_name,
			"auth_type": definition["auth_type"],
			"connection_status": "not_checked",
			**{key.partition(".")[2]: value for key, value in values.items() if key.startswith("api.")},
		}
	).insert()
	return {
		"provider": provider_name,
		"account": account,
		"api": api.name,
		"connection_status": "not_checked",
	}


def check_status(code):
	"""Map a fixed gateway code to the status shown on the form."""
	return CHECK_STATUS.get(code, "provider_error")


def _endpoint(api, account, provider):
	base = api.base_url or provider.default_url
	oauth_url = api.oauth_token_url if api.auth_type == "oauth_client_credentials" else ""
	if not base:
		raise adapters.GatewayError("configuration", may_be_billed=False)
	kind, addresses, oauth_addresses = policy.connection_policy(base, oauth_url)
	secret = (
		get_decrypted_password("PLT AI API", api.name, "api_key", raise_exception=False)
		if api.auth_type != "none"
		else ""
	)
	return adapters.Endpoint(
		api.name,
		provider.adapter,
		base,
		api.auth_type,
		secret or "",
		oauth_url,
		api.oauth_client_id or "",
		kind=kind,
		addresses=addresses,
		oauth_addresses=oauth_addresses,
		organization=account.organization_id or "",
		project=account.project_id or "",
	)


def _probe(api, account, provider):
	try:
		endpoint = _endpoint(api, account, provider)
	except Denied as failure:
		if failure.code != "endpoint_unavailable":
			raise
		return "endpoint_not_approved", None
	except adapters.GatewayError as failure:
		return check_status(failure.code), None
	try:
		count = adapters.list_models(endpoint, timeout=CHECK_TIMEOUT, connect_timeout=CHECK_CONNECT_TIMEOUT)
	except adapters.GatewayError as failure:
		return check_status(failure.code), None
	return "connected", count


def check_connection(api):
	"""Send one model-list request and record the result on the API connection."""
	policy.require_user(managers_only=True)
	gateway._require_clean_transaction()
	record = gateway._document("PLT AI API", api)
	record.check_permission("write")
	account = frappe.get_doc("PLT AI Account", record.account)
	provider = frappe.get_doc("PLT AI Provider", account.provider)
	lease = CHECK_TIMEOUT + CHECK_CONNECT_TIMEOUT + 5
	with gateway.scoped_lock("check", record.name, timeout=lease):
		status, count = _probe(record, account, provider)
	checked_at = now()
	values = {"connection_status": status, "connection_checked_at": checked_at}
	if status == "connected":
		values["health_status"] = "healthy"
	elif status == "invalid_credentials":
		values["health_status"] = "auth_failed"
	frappe.db.set_value("PLT AI API", record.name, values, update_modified=False)
	return {"api": record.name, "status": status, "checked_at": checked_at, "models_visible": count}
