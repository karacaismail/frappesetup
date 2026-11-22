"""İznin nedeni ve kapsam özeti. Sözleşme: `contracts/platform_core-erisim.openapi.yaml`."""

import frappe
import frappe.share
from frappe import _
from frappe.permissions import get_role_permissions, has_permission

from platform_core.erisim import engine, rules

SHAREABLE = ("read", "write", "submit")


def _require_doctype(doctype: str) -> None:
	if not frappe.db.exists("DocType", doctype, cache=True):
		frappe.throw(_("Document type {0} not found.").format(doctype), frappe.DoesNotExistError)


def explain(doctype: str, name: str, ptype: str = "read", user: str | None = None) -> dict:
	caller = frappe.session.user
	target = user or caller
	is_admin = caller == "Administrator" or "System Manager" in frappe.get_roles(caller)
	if target != caller and not is_admin:
		frappe.throw(
			_("Only a System Manager can explain another user's permission."), frappe.PermissionError
		)
	if ptype not in rules.OPERATIONS:
		frappe.throw(_("ptype must be one of: {0}").format(", ".join(rules.OPERATIONS)))
	_require_doctype(doctype)
	if target != caller and not frappe.db.exists("User", target):
		frappe.throw(_("User {0} not found.").format(target), frappe.DoesNotExistError)

	governed = rules.is_governed(doctype)
	result = {
		"doctype": doctype,
		"name": name,
		"ptype": ptype,
		"user": target,
		"allowed": False,
		"reason": "not_permitted_or_missing",
		"governed": governed,
		"layers": {"role": False, "access_rule": False, "share": False},
		"rules": [],
	}
	# Açıklama motorun kendi okumasıdır. Sonuç çağırana göre aşağıda daraltılır.
	owner = frappe.db.get_value(doctype, name, "owner")
	exists = owner is not None
	if not exists and is_admin:
		frappe.throw(_("{0} {1} not found.").format(doctype, name), frappe.DoesNotExistError)

	is_owner = exists and (owner or "").lower() == target.lower()
	role = bool(get_role_permissions(frappe.get_meta(doctype), user=target, is_owner=is_owner).get(ptype))
	result["layers"]["role"] = role
	if not exists:
		if not role:
			result["reason"] = "no_role_permission"
		return result

	allowed = has_permission(doctype, ptype, doc=name, user=target, print_logs=False)
	without_share = has_permission(
		doctype, ptype, doc=name, user=target, print_logs=False, ignore_share_permissions=True
	)
	by_rule, rule_report = engine.decide_stored(doctype, name, ptype, target)
	shared = ptype in SHAREABLE and bool(
		frappe.share.get_shared(doctype, target, rights=[ptype], filters=[["share_name", "=", name]], limit=1)
	)

	result["allowed"] = bool(allowed)
	if allowed:
		result["reason"] = "allowed" if without_share else "allowed_by_share"
		result["layers"].update(access_rule=by_rule, share=shared)
	elif not role:
		result["reason"] = "no_role_permission"
	elif is_admin:
		result["reason"] = "user_permission" if by_rule else "no_matching_rule"
		result["layers"].update(access_rule=by_rule, share=shared)
	if is_admin:
		result["rules"] = rule_report
	return result


def summary(doctype: str) -> dict:
	_require_doctype(doctype)
	user = frappe.session.user
	operations = {
		operation: sorted({rule["scope"] for rule in rules.applicable(doctype, user, operation)})
		for operation in rules.OPERATIONS
	}
	return {"doctype": doctype, "governed": rules.is_governed(doctype), "operations": operations}
