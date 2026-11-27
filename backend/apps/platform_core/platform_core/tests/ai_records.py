"""Test records of the AI provider types (AJA-947, AJA-1050).

The types "PLT AI Provider", "PLT AI Account" and "PLT AI API" belong to
platform_core.model_gateway. The access module may not write them (backend/dev/bin/module-boundaries).
The panel role tests of the access module use these helpers instead.
"""

from __future__ import annotations

import frappe


def insert_ai_records(suffix: str, api_key: str) -> dict[str, str]:
	"""Inserts one provider, account and API as the administrator. Returns the names by type."""
	provider = frappe.get_doc(
		doctype="PLT AI Provider", provider_name=f"PR Saglayici {suffix}", adapter="openai"
	).insert(ignore_permissions=True)
	account = frappe.get_doc(
		doctype="PLT AI Account",
		provider=provider.name,
		account_name=f"PR Hesap {suffix}",
		currency="USD",
	).insert(ignore_permissions=True)
	api = frappe.get_doc(
		doctype="PLT AI API",
		account=account.name,
		api_name=f"PR API {suffix}",
		base_url="https://saglayici.example.test",
		auth_type="api_key",
		api_key=api_key,
	).insert(ignore_permissions=True)
	return {"PLT AI Provider": provider.name, "PLT AI Account": account.name, "PLT AI API": api.name}


def remove_ai_records(names: dict[str, str]) -> None:
	for doctype in ("PLT AI API", "PLT AI Account", "PLT AI Provider"):
		name = names.get(doctype)
		if name and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
