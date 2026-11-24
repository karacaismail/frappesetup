"""G-10: prices are stored and shown in US dollars.

The orchestrator decided on 24 November 2026 that prices stay in US dollars for now. No Turkish
lira field is written. Press's own price checks read ``price_usd``, so a paid plan needs a dollar
price above zero and a free plan keeps zero. Press already gives a team from Türkiye the USD
currency (``Team.before_insert``), so press_tr changes no team currency.

The test needs no Frappe install: ``frappe`` is replaced with an in-memory stub.
"""

import csv
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from plan_stubs import APP_ROOT, FakeFrappe, Rejected, load

SOURCES = ("plans.py", "pricing.py", "pricing_schema.py", "hooks.py")


class PlanCurrencyTest(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe(self)
		(self.plans,) = load(self, self.fake, "press_tr.plans")

	def test_prices_are_us_dollars_from_one_place(self):
		self.assertEqual(self.plans.CURRENCY, "USD")
		prices = {plan["name"]: plan["price_usd"] for plan in self.plans.PLANS}
		self.assertEqual(
			prices,
			{
				"press-tr-starter": 400,
				"press-tr-growth": 750,
				"press-tr-enterprise": None,
				"press-tr-trial": 0,
			},
		)

	def test_migrate_writes_dollar_prices(self):
		self.plans.sync_plans()
		rows = self.fake.records["Site Plan"]
		self.assertEqual(rows["press-tr-starter"]["price_usd"], 400)
		self.assertEqual(rows["press-tr-growth"]["price_usd"], 750)
		# Press needs a number. The Enterprise plan is never listed to customers.
		self.assertEqual(rows["press-tr-enterprise"]["price_usd"], 0)
		self.assertEqual(rows["press-tr-trial"]["price_usd"], 0)
		self.assertTrue(all(row["price_inr"] == 0 for row in rows.values()))
		self.assertTrue(all("price_try" not in row for row in rows.values()))

	def test_paid_plans_have_a_price_above_zero_and_free_plans_have_zero(self):
		for plan in self.plans.PLANS:
			with self.subTest(plan=plan["name"]):
				if plan["trial"]:
					self.assertEqual(plan["price_usd"], 0)
				elif plan["self_service"]:
					self.assertGreater(plan["price_usd"], 0)
				else:
					self.assertIsNone(plan["price_usd"])

	def test_panel_plan_list_shows_dollars_and_a_contact_message(self):
		plans = {plan["name"]: plan for plan in self.plans.public_plans()}
		self.assertEqual(list(plans), [plan["name"] for plan in self.plans.PLANS])
		self.assertTrue(all(plan["currency"] == "USD" for plan in plans.values()))
		self.assertEqual(plans["press-tr-starter"]["price_usd"], 400)
		self.assertFalse(plans["press-tr-starter"]["contact_us"])
		enterprise = plans["press-tr-enterprise"]
		self.assertIsNone(enterprise["price_usd"])
		self.assertTrue(enterprise["contact_us"])
		self.assertFalse(enterprise["self_service"])
		self.assertEqual(plans["press-tr-trial"]["trial_days"], 14)
		self.assertIsNone(plans["press-tr-growth"]["trial_days"])


class PlanSchemaTest(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe(self)
		self.fields = Mock()
		self.setter = Mock()
		meta = SimpleNamespace(get_field=lambda name: SimpleNamespace(options="Info\nWarning"))
		extra = {
			"frappe.custom": SimpleNamespace(),
			"frappe.custom.doctype": SimpleNamespace(),
			"frappe.custom.doctype.custom_field": SimpleNamespace(),
			"frappe.custom.doctype.custom_field.custom_field": SimpleNamespace(create_custom_fields=self.fields),
			"frappe.custom.doctype.property_setter": SimpleNamespace(),
			"frappe.custom.doctype.property_setter.property_setter": SimpleNamespace(
				make_property_setter=self.setter
			),
			"press.press.doctype.communication_info.communication_info": SimpleNamespace(
				get_communication_info=Mock()
			),
		}
		(self.schema,) = load(self, self.fake, "press_tr.pricing_schema", extra_modules=extra)
		sys.modules["frappe"].get_meta = lambda doctype: meta

	def test_no_turkish_lira_field_is_created(self):
		self.schema.sync_pricing_fields()
		fields = self.fields.call_args.args[0]["Site Plan"]
		names = [field["fieldname"] for field in fields]
		self.assertEqual(names, ["price_effective_date", "price_previous_plan"])
		self.assertEqual(fields[0]["insert_after"], "price_usd")
		self.setter.assert_called_once()


class NoTurkishLiraTest(unittest.TestCase):
	def test_sources_have_no_turkish_lira_price(self):
		for name in SOURCES:
			text = (APP_ROOT / "press_tr" / name).read_text(encoding="utf-8")
			with self.subTest(source=name):
				self.assertNotIn("price_try", text)
				self.assertNotIn('"TRY"', text)

	def test_translations_have_no_turkish_lira_price(self):
		path = APP_ROOT / "press_tr/translations/tr.csv"
		with path.open(encoding="utf-8", newline="") as source:
			rows = [row for row in csv.reader(source) if row[2] == "press_tr"]
		self.assertFalse([row for row in rows if "Turkish lira" in row[0] or "TRY" in row[0]])

	def test_hooks_keep_press_dollar_pricing(self):
		(hooks,) = load(self, FakeFrappe(self), "press_tr.hooks")
		self.assertNotIn("Site Plan", hooks.extend_doctype_class)
		self.assertNotIn("press.api.site.get_site_plans", getattr(hooks, "override_whitelisted_methods", {}))


class PaidPlanPriceTest(unittest.TestCase):
	def test_paid_plan_price_change_needs_dollars_above_zero(self):
		fake = FakeFrappe(self)
		extra = {
			"press.press.doctype.communication_info.communication_info": SimpleNamespace(
				get_communication_info=Mock()
			)
		}
		(pricing,) = load(self, fake, "press_tr.pricing", extra_modules=extra)
		with self.assertRaises(Rejected):
			pricing.create_price_revision("press-tr-starter", "press-tr-starter-2027", "0", "2027-01-31")
		self.assertNotIn("Site Plan", fake.records)


if __name__ == "__main__":
	unittest.main()
