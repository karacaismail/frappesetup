"""Validate HRMS TR dependencies and manage its installation fixtures."""

import json
from pathlib import Path

import frappe
from frappe import _
from frappe.permissions import setup_custom_perms

from hrms_tr.access import DOCTYPE, RULE_DOCTYPE, engine_available
from hrms_tr.users import APPROVER_PROFILES, EMPLOYEE_ROLE, HRMS_TR_ROLES, NATIVE_LEAVE_APPROVER

RULE_FIXTURE = "03_access_rule.json"
OWNED_POLICY_FIXTURES = (RULE_FIXTURE, "04_property_setter.json", "05_custom_docperm.json")
USER_BATCH_SIZE = 100


def fixture_rows(filename):
	path = Path(frappe.get_app_path("hrms_tr", "fixtures", filename))
	return json.loads(path.read_text(encoding="utf-8"))


def require_access_engine():
	if not engine_available() or not frappe.db.exists("DocType", RULE_DOCTYPE):
		frappe.throw(_("Install Platform Core with Access Rule before syncing HRMS TR.", context="hrms_tr"))


def require_unshared_applications():
	if frappe.db.exists("DocShare", {"share_doctype": DOCTYPE}):
		frappe.throw(
			_("Resolve existing Leave Application shares before syncing HRMS TR.", context="hrms_tr")
		)


def check_install():
	require_access_engine()
	require_unshared_applications()
	if frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE, "permlevel": 2}):
		frappe.throw(
			_(
				"Resolve existing level 2 Leave Application permissions before installing HRMS TR.",
				context="hrms_tr",
			)
		)
	for row in fixture_rows("04_property_setter.json"):
		if frappe.db.exists(row["doctype"], row["name"]):
			frappe.throw(
				_(
					"Resolve existing leave balance field settings before installing HRMS TR.",
					context="hrms_tr",
				)
			)
	preserve_employee_permissions()


# Personal fields of an employee record sit on their own permission level (AJA-1024).
# The two tenant panel roles read level 0 of an employee: HRMS asks for it before a leave is
# opened. The HR roles that read the whole record before also read this level.
# `04_property_setter.json` moves the fields, `05_custom_docperm.json` gives the level.
EMPLOYEE_PERSONAL_LEVEL = 1
EMPLOYEE_PERSONAL_FIELDS = (
	"personal_email",
	# HRMS copies the preferred contact address here. It can be the personal address.
	"prefered_email",
	"cell_number",
	"date_of_birth",
	"date_of_retirement",
	"image",
	"current_address",
	"current_accommodation_type",
	"permanent_address",
	"permanent_accommodation_type",
	"person_to_be_contacted",
	"emergency_phone_number",
	"relation",
	"ctc",
	"salary_currency",
	"salary_mode",
	"bank_name",
	"bank_ac_no",
	"iban",
	"marital_status",
	"family_background",
	"blood_group",
	"health_details",
	"health_insurance_provider",
	"health_insurance_no",
	"passport_number",
	"valid_upto",
	"date_of_issue",
	"place_of_issue",
	"bio",
	"education",
	"external_work_history",
	"reason_for_leaving",
	"feedback",
	"new_workplace",
	"held_on",
	"resignation_letter_date",
	"leave_encashed",
	"encashment_date",
)
# The fields of the two personal child tables sit on the same level. Frappe checks a child
# table query against the field levels of the child type, not of the parent's table field.
EMPLOYEE_PERSONAL_CHILD_FIELDS = {
	"Employee Education": (
		"school_univ",
		"qualification",
		"level",
		"year_of_passing",
		"class_per",
		"maj_opt_subj",
	),
	"Employee External Work History": (
		"company_name",
		"designation",
		"salary",
		"address",
		"contact",
		"total_experience",
	),
}
EMPLOYEE_PERSONAL_CHILD_TYPES = tuple(EMPLOYEE_PERSONAL_CHILD_FIELDS)

# Types that get HRMS TR custom permission rows next to their standard ones.
# "Leave Type" gets "select" so a leave role can search the link field of a leave application.
PRESERVED_PERMISSION_DOCTYPES = ("Employee", "Leave Type")


def preserve_employee_permissions():
	# Frappe uses custom rows instead of the standard permissions once any custom row exists.
	for doctype in PRESERVED_PERMISSION_DOCTYPES:
		setup_custom_perms(doctype)


def before_migrate():
	require_access_engine()
	require_unshared_applications()
	preserve_employee_permissions()
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
			doc.save()

	# The administrator is synchronizing stored role profiles, not preparing a user-facing list.
	cursor = ""
	while True:
		names = frappe.get_all(
			"Has Role",
			filters=[["parenttype", "=", "User"], ["role", "in", HRMS_TR_ROLES], ["parent", ">", cursor]],
			distinct=True,
			pluck="parent",
			order_by="parent asc",
			limit_page_length=USER_BATCH_SIZE,
		)
		if not names:
			break
		sync_portal_user_batch(names)
		cursor = names[-1]


def sync_portal_user_batch(names):
	users = frappe.get_all(
		"User",
		filters={"name": ["in", names]},
		fields=["name", "user_type"],
		limit_page_length=USER_BATCH_SIZE,
	)
	roles = frappe.get_all(
		"Has Role",
		filters={
			"parenttype": "User",
			"parent": ["in", names],
			"role": ["in", [EMPLOYEE_ROLE, NATIVE_LEAVE_APPROVER]],
		},
		fields=["parent", "role"],
		distinct=True,
		limit_page_length=2 * USER_BATCH_SIZE,
	)
	employee_names = {row.parent for row in roles if row.role == EMPLOYEE_ROLE}
	legacy_approver_names = {row.parent for row in roles if row.role == NATIVE_LEAVE_APPROVER}
	approver_names = set(
		frappe.get_all(
			"User Role Profile",
			filters={"parent": ["in", names], "role_profile": ["in", APPROVER_PROFILES]},
			pluck="parent",
			distinct=True,
			limit_page_length=USER_BATCH_SIZE,
		)
	)
	for user in users:
		if user.name == "Administrator":
			continue
		missing_employee_role = user.name in approver_names and user.name not in employee_names
		if user.user_type != "Website User" or user.name in legacy_approver_names or missing_employee_role:
			frappe.get_doc("User", user.name).save()


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
			frappe.delete_doc(doctype, name)
	# The framework commits app removal before after_uninstall and does not commit again.
	frappe.db.commit()
	frappe.clear_cache(doctype=DOCTYPE)
	for doctype in PRESERVED_PERMISSION_DOCTYPES:
		frappe.clear_cache(doctype=doctype)
