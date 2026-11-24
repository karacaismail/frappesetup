"""G-9 and G-10: the press_tr plan set, the trial and the plan limits.

Every plan value lives in this file only. The product owner gave the prices on 24 November 2026.
Prices are stored and shown in US dollars. The Enterprise plan has no price: the panel shows a
contact message and an operator opens the tenant.

The plan limits are still open. They stay ``None`` until the product owner gives them, and each
plan with an empty limit warns on every migrate. Empty limits are never written to Press.

Migrate creates a missing plan closed (``enabled=0``). It never edits an existing plan record:
a price changes only through ``press_tr.pricing.create_price_revision``.
"""

import frappe

CURRENCY = "USD"
TRIAL_DAYS = 14
OPERATOR_ROLE = "System Manager"
CUSTOMER_ROLE = "Press User"
TRIAL_SETTING = ("Press Settings", "press_trial_plan")

# Press has fields for the first two limits only. The other three wait for a design decision.
PRESS_LIMIT_FIELDS = ("max_database_usage", "max_storage_usage")
LIMIT_FIELDS = (*PRESS_LIMIT_FIELDS, "backup_count", "role_count", "app_count")


def _plan(name, title, price_usd, *, self_service=True, trial=False):
	return {
		"name": name,
		"title": title,
		"price_usd": price_usd,
		"self_service": self_service,
		"trial": trial,
		"limits": dict.fromkeys(LIMIT_FIELDS),
	}


PLANS = (
	_plan("press-tr-starter", "Başlangıç", 400),
	_plan("press-tr-growth", "Büyüme", 750),
	# No price is written. The panel shows "Fiyat için bize ulaşın" for this plan.
	_plan("press-tr-enterprise", "Kurumsal", None, self_service=False),
	_plan("press-tr-trial", "Deneme", 0, trial=True),
)


def plan_names(*, self_service=None, trial=None):
	return [
		plan["name"]
		for plan in PLANS
		if (self_service is None or plan["self_service"] is self_service)
		and (trial is None or plan["trial"] is trial)
	]


def public_plans():
	"""The plan list for the panel, in US dollars. The Enterprise plan shows a contact message."""
	return [
		{
			"name": plan["name"],
			"title": plan["title"],
			"currency": CURRENCY,
			"price_usd": plan["price_usd"],
			"self_service": plan["self_service"],
			"contact_us": plan["price_usd"] is None,
			"trial_days": TRIAL_DAYS if plan["trial"] else None,
		}
		for plan in PLANS
	]


def missing_limits(plan):
	return [field for field in LIMIT_FIELDS if plan["limits"].get(field) is None]


def limit_warnings():
	warnings = []
	for plan in PLANS:
		missing = missing_limits(plan)
		if missing:
			message = frappe._("The {0} plan has missing limits: {1}.", context="press_tr")
			warnings.append(message.format(plan["title"], ", ".join(missing)))
	return warnings


def _site_plan(plan):
	role = CUSTOMER_ROLE if plan["self_service"] else OPERATOR_ROLE
	values = {
		"doctype": "Site Plan",
		"plan_title": plan["title"],
		"document_type": "Site",
		"interval": "Monthly",
		"price_usd": plan["price_usd"] or 0,
		"price_inr": 0,
		"is_trial_plan": int(plan["trial"]),
		"enabled": 0,
		# Press lists a plan only to the roles on it, so customers never see the Enterprise plan.
		"roles": [{"role": role}],
	}
	for field in PRESS_LIMIT_FIELDS:
		if plan["limits"][field] is not None:
			values[field] = plan["limits"][field]
	return values


def sync_plans():
	"""Create missing plans and point Press at our trial plan. Return the limit warnings."""
	for plan in PLANS:
		if not frappe.db.exists("Site Plan", plan["name"]):
			frappe.get_doc(_site_plan(plan)).insert(set_name=plan["name"], ignore_permissions=True)
	# The G-8 cleanup closes the Press trial plans, so Press must use ours.
	frappe.db.set_single_value(*TRIAL_SETTING, plan_names(trial=True)[0])
	warnings = limit_warnings()
	for warning in warnings:
		print(warning)
	return warnings


def reject_operator_plan(doc, method=None):
	"""Only an operator puts a subscription on the Enterprise plan."""
	if doc.get("plan_type") != "Site Plan" or doc.get("plan") not in plan_names(self_service=False):
		return
	if OPERATOR_ROLE not in frappe.get_roles():
		frappe.throw(frappe._("Contact us to open an Enterprise plan.", context="press_tr"))


def set_trial_end_date(doc, method=None):
	"""A new site on a trial plan gets its last trial day. Press sets it only for SaaS sites."""
	plan = doc.get("subscription_plan") or doc.get("plan")
	if doc.get("trial_end_date") or not plan:
		return
	if plan in plan_names(trial=True) or frappe.db.get_value("Site Plan", plan, "is_trial_plan"):
		doc.trial_end_date = frappe.utils.add_days(frappe.utils.getdate(), TRIAL_DAYS)


def suspend_expired_trials():
	"""Stop each active site whose trial ended. An operator runs this with ``bench execute``.

	Press has no step that stops a site when its trial ends. Choosing a paid plan runs Press's
	``Site.change_plan``, which unsuspends the site and clears ``trial_end_date``.
	"""
	frappe.only_for(OPERATOR_ROLE)
	press_trials = frappe.get_all("Site Plan", filters={"is_trial_plan": 1}, pluck="name")
	trial_plans = sorted({*plan_names(trial=True), *press_trials})
	sites = frappe.get_all(
		"Site",
		filters={
			"status": "Active",
			"plan": ["in", trial_plans],
			"trial_end_date": ["<", frappe.utils.getdate()],
		},
		pluck="name",
	)
	for name in sites:
		frappe.get_doc("Site", name).suspend(reason="Trial ended")
	return sites
