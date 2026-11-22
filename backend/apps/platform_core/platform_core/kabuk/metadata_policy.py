"""Site configuration and trusted request scope for metadata disclosure."""

from dataclasses import dataclass, field

import frappe

MOBILE_ROUTE_PREFIX = "/api/method/platform_core.api.mobile."


@dataclass
class MetadataPolicy:
	mobile_doctypes: set[str] = field(default_factory=set)
	restricted_doctypes: set[str] = field(default_factory=set)
	restricted_fields: dict[str, set[str]] = field(default_factory=dict)
	mobile_errors: list[str] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)

	def allows_mobile(self, doctype: str) -> bool:
		return doctype in self.mobile_doctypes and doctype not in self.restricted_doctypes


def load_metadata_policy() -> MetadataPolicy:
	policy = MetadataPolicy()
	for key, target in (
		("shell_mobile_doctypes", policy.mobile_doctypes),
		("shell_restricted_doctypes", policy.restricted_doctypes),
	):
		errors = policy.mobile_errors if key == "shell_mobile_doctypes" else policy.errors
		names = frappe.conf.get(key, [])
		if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
			errors.append(f"{key} must be an array of DocType names.")
			continue
		for name in names:
			if frappe.db.exists("DocType", name, cache=True) == name:
				target.add(name)
			else:
				errors.append(f"{key} contains an unknown DocType: {name}")

	configured_fields = frappe.conf.get("shell_restricted_fields", {})
	if not isinstance(configured_fields, dict):
		policy.errors.append("shell_restricted_fields must map DocType names to field names.")
		return policy
	for doctype, names in configured_fields.items():
		if not isinstance(doctype, str) or frappe.db.exists("DocType", doctype, cache=True) != doctype:
			policy.errors.append(f"shell_restricted_fields contains an unknown DocType: {doctype}")
			continue
		if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
			policy.errors.append(
				f"shell_restricted_fields entry for {doctype} must be an array of field names."
			)
			continue
		known = {item.fieldname for item in frappe.get_meta(doctype).fields}
		policy.restricted_fields[doctype] = set(names) & known
		for unknown in sorted(set(names) - known):
			policy.errors.append(f"shell_restricted_fields contains an unknown field: {doctype}.{unknown}")
	return policy


def validate_mobile_policy() -> dict:
	"""Report invalid metadata policy entries through the local Bench command."""
	policy = load_metadata_policy()
	errors = policy.errors + policy.mobile_errors
	return {"valid": not errors, "errors": errors}


def verified_mobile_request(user: str) -> bool:
	identity = getattr(frappe.local, "mobile_identity", None)
	request = getattr(frappe.local, "request", None)
	return bool(
		isinstance(identity, dict)
		and identity.get("account") == user
		and identity.get("scope") == "mobile"
		and identity.get("site") == frappe.local.site
		and all(
			isinstance(identity.get(key), str) and identity[key].strip() for key in ("installation", "sid")
		)
		and request
		and request.path.startswith(MOBILE_ROUTE_PREFIX)
	)
