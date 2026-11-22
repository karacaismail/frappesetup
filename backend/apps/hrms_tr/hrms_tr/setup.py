"""Validate HRMS TR dependencies and manage its installation fixtures."""

import json
from pathlib import Path

import frappe
from frappe import _

from hrms_tr.access import DOCTYPE, RULE_DOCTYPE, engine_available
from hrms_tr.users import HRMS_TR_ROLES, NATIVE_LEAVE_APPROVER

RULE_FIXTURE = "03_access_rule.json"
OWNED_POLICY_FIXTURES = (RULE_FIXTURE, "04_property_setter.json", "05_custom_docperm.json")


def fixture_rows(filename):
	path = Path(frappe.get_app_path("hrms_tr", "fixtures", filename))
	return json.loads(path.read_text(encoding="utf-8"))


def require_access_engine():
	if not engine_available() or not frappe.db.exists("DocType", RULE_DOCTYPE):
		frappe.throw(_("Install Platform Core with Access Rule before syncing HRMS TR."))


def require_unshared_applications():
	if frappe.db.exists("DocShare", {"share_doctype": DOCTYPE}):
		frappe.throw(_("Resolve existing Leave Application shares before syncing HRMS TR."))


def check_install():
	require_access_engine()
	require_unshared_applications()
	if frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE, "permlevel": 2}):
		frappe.throw(_("Resolve existing level 2 Leave Application permissions before installing HRMS TR."))
	for row in fixture_rows("04_property_setter.json"):
		if frappe.db.exists(row["doctype"], row["name"]):
			frappe.throw(_("Resolve existing leave balance field settings before installing HRMS TR."))


def before_migrate():
	require_access_engine()
	require_unshared_applications()
	frappe.local.hrms_tr_disabled_rules = frappe.get_all(
		RULE_DOCTYPE,
		filters={"name": ["in", [row["name"] for row in fixture_rows(RULE_FIXTURE)]], "is_active": 0},
		pluck="name",
	)


def after_migrate():
	for name in frappe.local.hrms_tr_disabled_rules:
		if frappe.db.get_value(RULE_DOCTYPE, name, "is_active"):
			doc = frappe.get_doc(RULE_DOCTYPE, name)
			doc.is_active = 0
			doc.save(ignore_permissions=True)

	user_names = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ["in", HRMS_TR_ROLES]},
		distinct=True,
		pluck="parent",
	)
	for name in user_names:
		if name == "Administrator":
			continue
		user = frappe.get_doc("User", name)
		if user.user_type != "Website User" or any(row.role == NATIVE_LEAVE_APPROVER for row in user.roles):
			user.save(ignore_permissions=True)


def policy_fixture_keys():
	return [
		(row["doctype"], row["name"]) for filename in OWNED_POLICY_FIXTURES for row in fixture_rows(filename)
	]


def before_uninstall():
	# Frappe also runs this hook during a dry run. Only collect owned names here.
	frappe.local.hrms_tr_uninstall_policy = policy_fixture_keys()


def after_uninstall():
	remove_policy_fixtures(frappe.local.hrms_tr_uninstall_policy)


def remove_policy_fixtures(keys=None):
	"""Remove owned permissions after a real uninstall; retries are safe."""
	if "hrms_tr" in frappe.get_installed_apps():
		return
	for doctype, name in policy_fixture_keys() if keys is None else keys:
		if frappe.db.exists("DocType", doctype) and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, ignore_permissions=True)
	# The framework commits app removal before after_uninstall and does not commit again.
	frappe.db.commit()
	frappe.clear_cache(doctype=DOCTYPE)
