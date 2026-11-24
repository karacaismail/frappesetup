"""G-9: change a Site Plan price with a new plan record and tell every subscriber team.

Press reads the current plan price when it records usage, so a price is never edited in place.
An operator runs ``create_price_revision`` with ``bench execute``. It is not an HTTP method:
the edge proxy keeps Press closed to customers. On the start day the operator enables the copy
by hand (PO decision in AJA-136, no scheduled job). Then subscribers move to the copy and the
old plan becomes a legacy plan.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

import frappe
from press.press.doctype.communication_info.communication_info import get_communication_info

from press_tr.plans import OPERATOR_ROLE, plan_names

PRICE_FIELDS = ("price_usd", "price_inr")
PRICE_PATTERN = re.compile(r"[0-9]{1,12}(?:\.[0-9]{1,2})?")
NOTICE_TYPE = "Site Plan Price Change"
NOTICE_DAYS = 30
MONTHS = (
	"Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
	"Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
)  # fmt: skip
WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def turkish_date(value: date) -> str:
	"""Write a date as "23 Aralık 2026 Çarşamba"."""
	return f"{value.day} {MONTHS[value.month - 1]} {value.year} {WEEKDAYS[value.weekday()]}"


def turkish_amount(value: Decimal) -> str:
	"""Write an amount as "1.250,00"."""
	return f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def parse_price(value: str) -> Decimal:
	if not isinstance(value, str) or not PRICE_PATTERN.fullmatch(value):
		frappe.throw(frappe._("Enter a price with at most two decimal places.", context="press_tr"))
	return Decimal(value)


def reject_price_edit(doc, method=None):
	before = doc.get_doc_before_save()
	if before and any((doc.get(field) or 0) != (before.get(field) or 0) for field in PRICE_FIELDS):
		frappe.throw(frappe._("Create a new plan to change its price.", context="press_tr"))
	if before and doc.get("price_previous_plan") != before.get("price_previous_plan"):
		frappe.throw(frappe._("You cannot change the previous plan.", context="press_tr"))

	effective_date = doc.get("price_effective_date")
	if before and str(effective_date or "") != str(before.get("price_effective_date") or ""):
		frappe.throw(frappe._("You cannot change the price start date.", context="press_tr"))
	if effective_date and doc.enabled and frappe.utils.getdate(effective_date) > frappe.utils.getdate():
		frappe.throw(frappe._("You can enable the plan when its price starts.", context="press_tr"))


def reject_early_subscription(doc, method=None):
	if doc.enabled and doc.plan_type == "Site Plan" and doc.plan:
		start = frappe.db.get_value("Site Plan", doc.plan, "price_effective_date")
		if start and frappe.utils.getdate(start) > frappe.utils.getdate():
			frappe.throw(frappe._("You can assign the plan when its price starts.", context="press_tr"))


def move_subscriptions_on_activation(doc, method=None):
	previous_plan = doc.get("price_previous_plan")
	before = doc.get_doc_before_save()
	if not previous_plan or not before or before.enabled or not doc.enabled:
		return

	subscriptions = frappe.get_all(
		"Subscription",
		filters={"plan_type": "Site Plan", "plan": previous_plan, "enabled": 1},
		pluck="name",
		order_by="name",
	)
	for name in subscriptions:
		subscription = frappe.get_doc("Subscription", name, for_update=True)
		if subscription.enabled and subscription.plan_type == "Site Plan" and subscription.plan == previous_plan:
			subscription.plan = doc.name
			subscription.save()
	# Press still bills a legacy plan, so a late subscription keeps working. New sites cannot
	# choose it, and a site on it may move to any other plan.
	frappe.db.set_value(
		"Site Plan",
		previous_plan,
		{"legacy_plan": 1, "allow_downgrading_from_other_plan": 1, "enabled": 0},
	)


def create_price_revision(plan: str, name: str, price_usd: str, effective_date: str) -> str:
	frappe.only_for(OPERATOR_ROLE)
	if not plan.strip() or not name.strip() or max(len(plan), len(name)) > 140:
		frappe.throw(frappe._("Enter valid plan names.", context="press_tr"))
	if plan in plan_names(self_service=False):
		frappe.throw(frappe._("The Enterprise plan has no price.", context="press_tr"))

	try:
		start = date.fromisoformat(effective_date)
		if start.isoformat() != effective_date:
			raise ValueError
	except ValueError:
		frappe.throw(frappe._("Enter a valid price start date.", context="press_tr"))

	if start < frappe.utils.getdate() + timedelta(days=NOTICE_DAYS):
		frappe.throw(frappe._("Choose a start date at least 30 days from today.", context="press_tr"))

	dollars = parse_price(price_usd)
	if not dollars:
		frappe.throw(frappe._("A paid plan needs a US dollar price above zero.", context="press_tr"))

	original = frappe.get_doc("Site Plan", plan)
	if dollars == Decimal(str(original.price_usd or 0)):
		frappe.throw(frappe._("Enter a price that differs from the current price.", context="press_tr"))

	# Use the full subscriber list for this operator task. The caller receives only the new plan name.
	teams = frappe.get_all(
		"Subscription",
		filters={"plan_type": "Site Plan", "plan": original.name, "enabled": 1},
		pluck="team",
		distinct=True,
	)
	recipients_by_team = {team: get_communication_info("Email", "General", "Team", team) for team in teams}
	if any(not recipients for recipients in recipients_by_team.values()):
		frappe.throw(
			frappe._(
				"Add an email address for each subscriber team before changing the price.", context="press_tr"
			)
		)

	successor = frappe.copy_doc(original)
	successor.price_usd = dollars
	successor.price_inr = 0
	successor.price_effective_date = start
	successor.price_previous_plan = original.name
	successor.enabled = 0
	successor.legacy_plan = 0
	successor.insert(set_name=name)

	subject = frappe._("Site plan price change", lang="tr", context="press_tr")
	message = frappe._(
		"The new monthly plan price is {0} US dollars from {1}.", lang="tr", context="press_tr"
	).format(turkish_amount(dollars), turkish_date(start))
	for team, recipients in recipients_by_team.items():
		notify_team(team, original.name, successor.name, subject, message, recipients)
	return successor.name


def notify_team(team, plan, successor, subject, message, recipients):
	notice = frappe.get_doc(
		{
			"doctype": "Press Notification",
			"type": NOTICE_TYPE,
			"team": team,
			"document_type": "Site Plan",
			"document_name": plan,
			"reference_doctype": "Site Plan",
			"reference_name": successor,
			"class": "Info",
			"title": subject,
			"message": message,
		}
	).insert()
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		reference_doctype=notice.doctype,
		reference_name=notice.name,
		now=True,
	)

